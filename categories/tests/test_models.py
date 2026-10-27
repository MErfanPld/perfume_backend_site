from django.test import TestCase

from categories.models import Category
from products.models import Product


class CategoryModelTests(TestCase):
    def test_create_category_and_link_product(self):
        cat = Category.objects.create(
            source_site="mehrdadgallery",
            source_category_id="10",
            name="مردانه",
            source_url="https://mehrdadgallery.com/product-category/men/",
        )
        self.assertTrue(cat.slug)
        self.assertTrue(cat.is_active)

        product = Product.objects.create(
            source_site="mehrdadgallery",
            source_product_id="52474",
            name="ادکلن تست",
            product_url="https://mehrdadgallery.com/product/test/",
            availability="in_stock",
        )
        product.categories.add(cat)
        self.assertEqual(product.categories.count(), 1)
        self.assertEqual(cat.products.count(), 1)

    def test_unique_source_category_id(self):
        Category.objects.create(
            source_site="mehrdadgallery",
            source_category_id="20",
            name="زنانه",
        )
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            Category.objects.create(
                source_site="mehrdadgallery",
                source_category_id="20",
                name="زنانه ۲",
            )
