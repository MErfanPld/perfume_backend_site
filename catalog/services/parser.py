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


def parse_listing_html(html: str, base_url: str = "https://mehrdadgallery.com") -> list[ParsedProduct]:
    """
    Parse a shop/category listing page HTML and return product cards.

    Selectors are based on the structure previously observed on mehrdadgallery.com
    (WooCommerce product cards with add-to-cart links and price text).
    """
    if not html or not html.strip():
        return []

    soup = BeautifulSoup(html, "html.parser")
    products: list[ParsedProduct] = []
    seen_ids: set[str] = set()

    # Primary strategy: find anchors that contain add-to-cart=ID
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        m = _ADD_TO_CART_RE.search(href)
        if not m:
            continue
        pid = m.group(1)
        if pid in seen_ids:
            continue
        seen_ids.add(pid)

        # Climb to a reasonable card container
        card = a
        for _ in range(6):
            parent = card.parent
            if parent is None or parent.name in ("body", "html"):
                break
            card = parent
            # Prefer li or div that looks like a product card
            classes = " ".join(card.get("class") or [])
            if any(k in classes for k in ("product", "type-product", "woocommerce")):
                break

        card_text = card.get_text(" ", strip=True)
        name = ""
        product_url = None

        # Prefer a product permalink
        for link in card.find_all("a", href=True):
            h = link.get("href", "")
            if "/product/" in h and "add-to-cart" not in h:
                product_url = _absolute_url(base_url, h)
                name = link.get_text(strip=True) or name
                if name:
                    break

        if not product_url:
            # fallback: any /product/ link near the card
            for link in card.find_all("a", href=True):
                h = link.get("href", "")
                if "/product/" in h:
                    product_url = _absolute_url(base_url, h)
                    if not name:
                        name = link.get_text(strip=True)
                    break

        if not name:
            # try heading
            for tag in card.find_all(["h2", "h3", "h4", "a"]):
                t = tag.get_text(strip=True)
                if t and len(t) > 5 and "تومان" not in t and "افزودن" not in t:
                    name = t
                    break

        if not name:
            name = f"Product {pid}"

        if not product_url:
            product_url = f"{base_url.rstrip('/')}/?p={pid}"

        regular, sale = extract_prices_from_text(card_text)
        availability = detect_availability(card_text)

        image_url = None
        img = card.find("img")
        if img:
            image_url = _absolute_url(
                base_url, img.get("src") or img.get("data-src") or img.get("data-lazy-src")
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
                stock_quantity=None,  # never invent
                image_url=image_url,
                raw_data={
                    "card_text_snippet": card_text[:300],
                    "add_to_cart_href": href,
                },
            )
        )

    # Secondary strategy: product title links when no add-to-cart was found
    # (out-of-stock items often show "اطلاعات بیشتر" instead of add-to-cart)
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if "/product/" not in href:
            continue
        # skip if we already captured via add-to-cart
        abs_url = _absolute_url(base_url, href) or href
        if any(p.product_url == abs_url for p in products):
            continue

        card = link
        for _ in range(5):
            parent = card.parent
            if parent is None:
                break
            card = parent
            classes = " ".join(card.get("class") or [])
            if any(k in classes for k in ("product", "type-product")):
                break

        card_text = card.get_text(" ", strip=True)
        name = link.get_text(strip=True) or "Unknown product"
        # Try to find an ID somewhere in the card (data attributes, etc.)
        pid = None
        for el in card.find_all(True):
            for attr, val in (el.attrs or {}).items():
                if isinstance(val, str) and val.isdigit() and len(val) >= 4:
                    if "product" in attr.lower() or "id" in attr.lower():
                        pid = val
                        break
            if pid:
                break
        if not pid:
            # derive a stable-ish key from the URL slug
            slug = href.rstrip("/").split("/")[-1]
            pid = f"slug:{slug[:80]}"

        if pid in seen_ids:
            continue
        seen_ids.add(pid)

        regular, sale = extract_prices_from_text(card_text)
        availability = detect_availability(card_text)

        image_url = None
        img = card.find("img")
        if img:
            image_url = _absolute_url(
                base_url, img.get("src") or img.get("data-src") or img.get("data-lazy-src")
            )

        products.append(
            ParsedProduct(
                source_product_id=pid,
                name=name[:512],
                product_url=abs_url,
                regular_price=regular,
                sale_price=sale,
                currency="تومان",
                availability=availability,
                stock_quantity=None,
                image_url=image_url,
                raw_data={"card_text_snippet": card_text[:300], "source": "permalink"},
            )
        )

    return products
