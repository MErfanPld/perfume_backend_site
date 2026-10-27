from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase

from products.models import Product
from products.services.importer import (
    SourceUnavailableError,
    import_products,
    run_import_from_fixture,
    upsert_product,
)
from products.services.parser import ParsedProduct

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "mehrdadgallery_shop_sample.html"


class UpsertTests(TestCase):
    def test_create_product(self):
        parsed = ParsedProduct(
            source_product_id="1001",
            name="Test Perfume",
            product_url="https://example.com/p/1001",
            regular_price=Decimal("1000000"),
            sale_price=Decimal("800000"),
            availability="in_stock",
            stock_quantity=None,
        )
        obj, created = upsert_product(parsed, source_site="test")
        self.assertTrue(created)
        self.assertEqual(obj.source_product_id, "1001")
        self.assertIsNone(obj.stock_quantity)
        self.assertEqual(obj.availability, "in_stock")
        self.assertIsNotNone(obj.last_successful_sync_at)

    def test_update_without_duplicate(self):
        parsed = ParsedProduct(
            source_product_id="1002",
            name="Original",
            product_url="https://example.com/p/1002",
            regular_price=Decimal("500000"),
            availability="in_stock",
        )
        upsert_product(parsed, source_site="test")
        parsed2 = ParsedProduct(
            source_product_id="1002",
            name="Updated Name",
            product_url="https://example.com/p/1002",
            regular_price=Decimal("450000"),
            availability="out_of_stock",
        )
        obj, created = upsert_product(parsed2, source_site="test")
        self.assertFalse(created)
        self.assertEqual(Product.objects.filter(source_site="test", source_product_id="1002").count(), 1)
        self.assertEqual(obj.name, "Updated Name")
        self.assertEqual(obj.regular_price, Decimal("450000"))
        self.assertEqual(obj.availability, "out_of_stock")

    def test_missing_price_does_not_clear_existing(self):
        parsed = ParsedProduct(
            source_product_id="1003",
            name="Has Price",
            product_url="https://example.com/p/1003",
            regular_price=Decimal("200000"),
            availability="in_stock",
        )
        upsert_product(parsed, source_site="test")
        # Second pass with no price parsed
        parsed2 = ParsedProduct(
            source_product_id="1003",
            name="Has Price",
            product_url="https://example.com/p/1003",
            regular_price=None,
            availability="in_stock",
        )
        obj, _ = upsert_product(parsed2, source_site="test")
        self.assertEqual(obj.regular_price, Decimal("200000"))


class ImportFromFixtureTests(TestCase):
    def test_import_fixture_creates_rows(self):
        stats = run_import_from_fixture(FIXTURE, source_site="mehrdadgallery", limit=5)
        self.assertEqual(stats["errors"], 0)
        self.assertGreaterEqual(stats["created"], 4)
        self.assertEqual(Product.objects.filter(source_site="mehrdadgallery").count(), stats["created"])
        # stock_quantity must remain null
        for p in Product.objects.all():
            self.assertIsNone(p.stock_quantity)

    def test_reimport_updates_not_duplicates(self):
        run_import_from_fixture(FIXTURE, source_site="mehrdadgallery", limit=5)
        first_count = Product.objects.count()
        stats = run_import_from_fixture(FIXTURE, source_site="mehrdadgallery", limit=5)
        self.assertEqual(stats["created"], 0)
        self.assertGreaterEqual(stats["updated"], 1)
        self.assertEqual(Product.objects.count(), first_count)


class NetworkErrorTests(TestCase):
    @patch("products.services.importer.urlopen")
    def test_source_unavailable(self, mock_urlopen):
        from products.services.importer import fetch_html

        mock_urlopen.side_effect = TimeoutError("timed out")
        with self.assertRaises(SourceUnavailableError):
            fetch_html("https://mehrdadgallery.com/shop/")
