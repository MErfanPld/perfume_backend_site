"""
Import orchestration: fetch (or load fixture) → parse → upsert Product records.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from products.models import Product
from products.services.parser import ParsedProduct, parse_listing_html

logger = logging.getLogger(__name__)


class SourceUnavailableError(Exception):
    """Raised when the remote source cannot be reached."""


def fetch_html(url: str, timeout: int | None = None, user_agent: str | None = None) -> str:
    timeout = timeout or getattr(settings, "IMPORT_REQUEST_TIMEOUT", 15)
    user_agent = user_agent or getattr(
        settings,
        "IMPORT_USER_AGENT",
        "Mozilla/5.0 (compatible; PerfumeImportBot/0.1)",
    )
    req = Request(url, headers={"User-Agent": user_agent, "Accept": "text/html"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise SourceUnavailableError(f"Failed to fetch {url}: {exc}") from exc


def load_fixture(path: Path | str) -> str:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Fixture not found: {p}")
    return p.read_text(encoding="utf-8")


def upsert_product(
    parsed: ParsedProduct,
    source_site: str,
) -> tuple[Product, bool]:
    """
    Create or update a Product. Returns (instance, created).
    Does not overwrite existing non-null fields with None/empty values.
    """
    defaults = {
        "name": parsed.name,
        "product_url": parsed.product_url,
        "currency": parsed.currency or "تومان",
        "availability": parsed.availability,
        "raw_data": parsed.raw_data or {},
    }
    # Only set prices / image when we actually parsed them
    if parsed.regular_price is not None:
        defaults["regular_price"] = parsed.regular_price
    if parsed.sale_price is not None:
        defaults["sale_price"] = parsed.sale_price
    if parsed.image_url:
        defaults["image_url"] = parsed.image_url
    # stock_quantity stays null unless an explicit integer was provided
    if parsed.stock_quantity is not None:
        defaults["stock_quantity"] = parsed.stock_quantity

    now = timezone.now()
    defaults["source_last_seen_at"] = now
    defaults["last_successful_sync_at"] = now

    obj, created = Product.objects.update_or_create(
        source_site=source_site,
        source_product_id=parsed.source_product_id,
        defaults=defaults,
    )

    if not created:
        # Defensive: avoid clearing previously known prices with missing data
        changed = False
        if parsed.regular_price is not None and obj.regular_price != parsed.regular_price:
            obj.regular_price = parsed.regular_price
            changed = True
        if parsed.sale_price is not None and obj.sale_price != parsed.sale_price:
            obj.sale_price = parsed.sale_price
            changed = True
        if parsed.availability and obj.availability != parsed.availability:
            obj.availability = parsed.availability
            changed = True
        if parsed.name and obj.name != parsed.name:
            obj.name = parsed.name
            changed = True
        if changed:
            obj.source_last_seen_at = now
            obj.last_successful_sync_at = now
            obj.save()

    return obj, created


@transaction.atomic
def import_products(
    products: Iterable[ParsedProduct],
    source_site: str | None = None,
    limit: int | None = None,
) -> dict:
    source_site = source_site or getattr(settings, "SOURCE_SITE_ID", "mehrdadgallery")
    limit = limit if limit is not None else getattr(settings, "IMPORT_DEFAULT_LIMIT", 5)

    stats = {"created": 0, "updated": 0, "skipped": 0, "errors": 0}
    count = 0
    for parsed in products:
        if limit is not None and count >= limit:
            break
        count += 1
        try:
            if not parsed.source_product_id or not parsed.name:
                stats["skipped"] += 1
                logger.warning("Skipping incomplete product: %s", parsed)
                continue
            _, created = upsert_product(parsed, source_site=source_site)
            if created:
                stats["created"] += 1
                logger.info("Created product %s (%s)", parsed.source_product_id, parsed.name[:60])
            else:
                stats["updated"] += 1
                logger.info("Updated product %s (%s)", parsed.source_product_id, parsed.name[:60])
        except Exception as exc:  # noqa: BLE001
            stats["errors"] += 1
            logger.exception("Error importing product %s: %s", parsed.source_product_id, exc)
    return stats

def run_import_from_url(
    url: str,
    source_site: str | None = None,
    limit: int | None = None,
    base_url: str | None = None,
) -> dict:
    from urllib.parse import urljoin
    from bs4 import BeautifulSoup

    base = base_url or getattr(
        settings, "SOURCE_BASE_URL", "https://mehrdadgallery.com"
    )
    limit = limit if limit is not None else getattr(
        settings, "IMPORT_DEFAULT_LIMIT", None
    )

    stats = {"created": 0, "updated": 0, "skipped": 0, "errors": 0}
    visited = set()
    current_url = url
    count = 0

    while current_url and current_url not in visited:
        if limit is not None and count >= limit:
            break

        visited.add(current_url)
        html = fetch_html(current_url)
        products = parse_listing_html(html, base_url=base)

        remaining = None if limit is None else limit - count
        page_stats = import_products(
            products if remaining is None else products[:remaining],
            source_site=source_site,
            limit=remaining,
        )

        for key in stats:
            stats[key] += page_stats[key]
        count += len(products if remaining is None else products[:remaining])

        soup = BeautifulSoup(html, "html.parser")
        next_link = (
            soup.select_one("a.next.page-numbers")
            or soup.select_one("a[rel='next']")
        )
        current_url = (
            urljoin(current_url, next_link.get("href"))
            if next_link and next_link.get("href")
            else None
        )

    return stats


def run_import_from_fixture(
    fixture_path: Path | str,
    source_site: str | None = None,
    limit: int | None = None,
    base_url: str | None = None,
) -> dict:
    html = load_fixture(fixture_path)
    base = base_url or getattr(
        settings, "SOURCE_BASE_URL", "https://mehrdadgallery.com"
    )
    parsed = parse_listing_html(html, base_url=base)
    return import_products(parsed, source_site=source_site, limit=limit)