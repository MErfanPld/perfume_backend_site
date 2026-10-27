from decimal import Decimal
from pathlib import Path

from django.test import TestCase

from catalog.services.parser import (
    detect_availability,
    extract_prices_from_text,
    normalize_digits,
    parse_listing_html,
    parse_price_number,
)

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "mehrdadgallery_shop_sample.html"


class DigitAndPriceTests(TestCase):
    def test_normalize_persian_digits(self):
        self.assertEqual(normalize_digits("۳۸۰.۰۰۰"), "380.000")
        self.assertEqual(normalize_digits("0123"), "0123")

    def test_parse_price_with_thousands_separators(self):
        self.assertEqual(parse_price_number("5.980.000 تومان"), Decimal("5980000"))
        self.assertEqual(parse_price_number("۳۸۰.۰۰۰ تومان"), Decimal("380000"))
        self.assertEqual(parse_price_number("880.000"), Decimal("880000"))

    def test_parse_price_invalid(self):
        self.assertIsNone(parse_price_number(""))
        self.assertIsNone(parse_price_number("no number here"))

    def test_extract_regular_and_sale(self):
        text = "5.980.000 تومان قیمت اصلی: 5.980.000 تومان بود. 3.580.000 تومان قیمت فعلی"
        regular, sale = extract_prices_from_text(text)
        self.assertEqual(regular, Decimal("5980000"))
        self.assertEqual(sale, Decimal("3580000"))

    def test_extract_single_price(self):
        regular, sale = extract_prices_from_text("380.000 تومان")
        self.assertEqual(regular, Decimal("380000"))
        self.assertIsNone(sale)


class AvailabilityTests(TestCase):
    def test_in_stock_label(self):
        self.assertEqual(detect_availability("افزودن به سبد خرید"), "in_stock")

    def test_out_of_stock_label(self):
        self.assertEqual(detect_availability("ناموجود - اطلاعات بیشتر"), "out_of_stock")

    def test_unknown(self):
        self.assertEqual(detect_availability("something else"), "unknown")


class ListingParseTests(TestCase):
    def test_parse_fixture_products(self):
        html = FIXTURE.read_text(encoding="utf-8")
        products = parse_listing_html(html)
        self.assertGreaterEqual(len(products), 5)

        by_id = {p.source_product_id: p for p in products}
        self.assertIn("52474", by_id)
        p = by_id["52474"]
        self.assertIn("التیر", p.name)
        self.assertEqual(p.regular_price, Decimal("5980000"))
        self.assertEqual(p.sale_price, Decimal("3580000"))
        self.assertEqual(p.availability, "in_stock")
        self.assertIsNone(p.stock_quantity)  # never invent
        self.assertTrue(p.product_url.startswith("https://"))

        self.assertIn("41587", by_id)
        self.assertEqual(by_id["41587"].availability, "in_stock")

        # Out-of-stock item without add-to-cart still parsed via secondary path
        out_items = [p for p in products if p.availability == "out_of_stock"]
        self.assertTrue(len(out_items) >= 1)
        for oi in out_items:
            self.assertIsNone(oi.stock_quantity)

    def test_persian_digits_in_fixture(self):
        html = FIXTURE.read_text(encoding="utf-8")
        products = parse_listing_html(html)
        by_id = {p.source_product_id: p for p in products}
        p = by_id.get("59148")
        self.assertIsNotNone(p)
        self.assertEqual(p.regular_price, Decimal("380000"))
        self.assertEqual(p.sale_price, Decimal("225000"))

    def test_empty_html(self):
        self.assertEqual(parse_listing_html(""), [])
        self.assertEqual(parse_listing_html("   "), [])

    def test_malformed_html_does_not_crash(self):
        products = parse_listing_html("<div><a href='/?add-to-cart=99'>x</a>")
        self.assertTrue(isinstance(products, list))
