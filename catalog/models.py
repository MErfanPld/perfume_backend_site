from django.db import models
from django.utils import timezone


class Product(models.Model):
    """Minimal product record imported from an external source (e.g. Mehrdad Gallery)."""

    class Availability(models.TextChoices):
        IN_STOCK = "in_stock", "In stock"
        OUT_OF_STOCK = "out_of_stock", "Out of stock"
        UNKNOWN = "unknown", "Unknown"

    source_site = models.CharField(max_length=64, db_index=True)
    source_product_id = models.CharField(max_length=64, db_index=True)
    name = models.CharField(max_length=512)
    product_url = models.URLField(max_length=1024)
    regular_price = models.DecimalField(
        max_digits=14, decimal_places=0, null=True, blank=True
    )
    sale_price = models.DecimalField(
        max_digits=14, decimal_places=0, null=True, blank=True
    )
    currency = models.CharField(max_length=32, default="تومان")
    availability = models.CharField(
        max_length=20,
        choices=Availability.choices,
        default=Availability.UNKNOWN,
    )
    # Explicitly nullable: null means "quantity unknown", never invent a number.
    stock_quantity = models.PositiveIntegerField(null=True, blank=True, default=None)
    image_url = models.URLField(max_length=1024, null=True, blank=True)
    source_last_seen_at = models.DateTimeField(null=True, blank=True)
    last_successful_sync_at = models.DateTimeField(null=True, blank=True)
    raw_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source_site", "source_product_id"],
                name="uniq_source_product",
            )
        ]
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.source_site}:{self.source_product_id})"

    def mark_synced(self) -> None:
        now = timezone.now()
        self.source_last_seen_at = now
        self.last_successful_sync_at = now
