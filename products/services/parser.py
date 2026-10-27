"""
HTML parser for Mehrdad Gallery (WooCommerce) product listing cards.

Designed against the publicly observed listing structure:
- product cards with links to /product/...
- add-to-cart=NUMERIC_ID
- price text containing تومان and optional "قیمت اصلی" / "قیمت فعلی"
- "ناموجود" label for out-of-stock items

This module does NOT invent stock quantities. stock_quantity is always None
unless an explicit numeric quantity is present in the source HTML.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

# Persian / Arabic-Indic digits → Western
_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

_PRICE_RE = re.compile(
    r"([\d۰-۹٠-٩][\d۰-۹٠-٩.,٬\s]*)\s*تومان",
    re.UNICODE,
)
_ADD_TO_CART_RE = re.compile(r"add-to-cart=(\d+)", re.IGNORECASE)
_PRODUCT_URL_RE = re.compile(r"/product/[^\"'\s?#]+", re.IGNORECASE)


@dataclass
class ParsedProduct:
    source_product_id: str
    name: str
    product_url: str
    regular_price: Decimal | None = None
    sale_price: Decimal | None = None
    currency: str = "تومان"
    availability: str = "unknown"
    stock_quantity: int | None = None
    image_url: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)


def normalize_digits(text: str) -> str:
    """Convert Persian/Arabic-Indic digits to ASCII digits."""
    if not text:
        return ""
    return text.translate(_PERSIAN_DIGITS)


def parse_price_number(text: str) -> Decimal | None:
    """
    Extract a numeric price from a localized string.
    Handles Persian digits, thousands separators (., ٬, spaces), and تومان.
    Iranian prices use '.' or '٬' as thousands separators (not decimal points).
    Returns None if no valid number is found.
    """
    if not text:
        return None
    normalized = normalize_digits(text)
    # Keep only the first plausible price-like token sequence
    match = re.search(r"[\d][\d.,٬\s]*", normalized)
    if not match:
        return None
    raw = match.group(0)
    # Remove all thousands separators and spaces; treat remaining digits as integer
    cleaned = re.sub(r"[.,٬\s]", "", raw)
    if not cleaned.isdigit():
        return None
    try:
        value = Decimal(cleaned)
        if value < 0:
            return None
        return value
    except (InvalidOperation, ValueError):
        return None


def extract_prices_from_text(text: str) -> tuple[Decimal | None, Decimal | None]:
    """
    Return (regular_price, sale_price) from a card text block.
    Common patterns observed:
      "5.980.000 تومان قیمت اصلی: 5.980.000 تومان بود. 3.580.000 تومان قیمت فعلی"
      "380.000 تومان"
    """
    if not text:
        return None, None

    normalized = normalize_digits(text)
    amounts = _PRICE_RE.findall(normalized)
    numbers: list[Decimal] = []
    for amount in amounts:
        num = parse_price_number(amount + " تومان")
        if num is not None:
            numbers.append(num)

    if not numbers:
        return None, None
    if len(numbers) == 1:
        return numbers[0], None
    # Heuristic: first is often regular, last is current/sale when both present
    regular = max(numbers)
    sale = min(numbers)
    if regular == sale:
        return regular, None
    return regular, sale


def detect_availability(text: str) -> str:
    """Map observed labels to availability status. Never invent quantities."""
    if not text:
        return "unknown"
    lower = text.lower()
    if "ناموجود" in text or "out of stock" in lower or "outofstock" in lower:
        return "out_of_stock"
    if "افزودن به سبد خرید" in text or "add to cart" in lower or "in stock" in lower:
        return "in_stock"
    return "unknown"


def _absolute_url(base: str, href: str | None) -> str | None:
    if not href:
        return None
    return urljoin(base, href)



def parse_listing_html(
    html: str,
    base_url: str = "https://mehrdadgallery.com",
) -> list[ParsedProduct]:
    """Parse WooCommerce product cards without inventing product IDs."""
    if not html or not html.strip():
        return []

    soup = BeautifulSoup(html, "html.parser")
    products: list[ParsedProduct] = []
    seen_ids: set[str] = set()

    # Prefer WooCommerce product cards; fall back to permalink-based discovery.
    cards = soup.select("li.product, div.product-grid-item, div.type-product")
    if not cards:
        cards = []

    for card in cards:
        product_link = card.select_one(
            "h2 a[href*='/product/'], h3 a[href*='/product/'], "
            ".wd-entities-title a[href*='/product/'], "
            "a.woocommerce-LoopProduct-link[href*='/product/']"
        )

        if product_link is None:
            for link in card.find_all("a", href=True):
                href = link.get("href", "")
                if "/product/" in href and "/product-category/" not in href:
                    product_link = link
                    break

        if product_link is None:
            continue

        product_url = _absolute_url(base_url, product_link.get("href"))
        if not product_url:
            continue

        # Use the actual WooCommerce post ID or add-to-cart ID only.
        pid = ""
        classes = card.get("class") or []
        for cls in classes:
            match = re.search(r"(?:^|-)post-(\d+)(?:$|-)", cls)
            if match:
                pid = match.group(1)
                break

        if not pid:
            for node in [card, *card.find_all(True)]:
                for attr in ("data-product_id", "data-product-id", "data-id"):
                    value = node.get(attr)
                    if value and str(value).isdigit():
                        pid = str(value)
                        break
                if pid:
                    break

        if not pid:
            for link in card.find_all("a", href=True):
                match = _ADD_TO_CART_RE.search(link.get("href", ""))
                if match:
                    pid = match.group(1)
                    break

        # Do not create synthetic IDs from slugs.
        if not pid or pid in seen_ids:
            continue
        seen_ids.add(pid)

        # Prefer explicit product title elements; discount labels are not names.
        title_node = card.select_one(
            "h2.woocommerce-loop-product__title, "
            "h3.woocommerce-loop-product__title, "
            ".wd-entities-title, h2, h3, h4"
        )
        name = ""
        if title_node:
            title_link = title_node.find("a", href=True)
            name = (
                title_link.get_text(" ", strip=True)
                if title_link
                else title_node.get_text(" ", strip=True)
            )

        if not name:
            name = product_link.get_text(" ", strip=True)

        name = re.sub(r"\s+", " ", name).strip()
        if (
            not name
            or re.fullmatch(r"-?\s*\d+\s*%", name)
            or "افزودن به سبد خرید" in name
        ):
            continue

        card_text = card.get_text(" ", strip=True)
        regular, sale = extract_prices_from_text(card_text)
        availability = detect_availability(card_text)

        image_url = None
        img = card.find("img")
        if img:
            image_url = _absolute_url(
                base_url,
                img.get("data-src")
                or img.get("data-lazy-src")
                or img.get("src")
                or img.get("data-srcset"),
            )

        products.append(
            ParsedProduct(
                source_product_id=pid,
                name=name[:512],
                product_url=product_url,
                regular_price=regular,
                sale_price=sale,
                currency="تومان",
                availability=availability,
                stock_quantity=None,
                image_url=image_url,
                raw_data={
                    "card_text_snippet": card_text[:300],
                    "source": "woocommerce_product_card",
                },
            )
        )

    return products
