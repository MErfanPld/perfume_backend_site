from django.contrib import admin

from categories.models import Category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "source_category_id",
        "parent",
        "is_active",
        "last_successful_sync_at",
    )
    list_filter = ("source_site", "is_active")
    search_fields = ("name", "source_category_id", "slug")
    readonly_fields = ("created_at", "updated_at", "last_successful_sync_at")
    prepopulated_fields = {"slug": ("name",)}
