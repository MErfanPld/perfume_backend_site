from django.contrib import admin

from products.models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "source_site",
        "source_product_id",
        "regular_price",
        "sale_price",
        "availability",
        "stock_quantity",
        "last_successful_sync_at",
    )
    list_filter = ("source_site", "availability")
    search_fields = ("name", "source_product_id", "product_url")
    readonly_fields = ("created_at", "updated_at", "source_last_seen_at", "last_successful_sync_at")
