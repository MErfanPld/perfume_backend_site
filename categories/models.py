from django.db import models
from django.utils.text import slugify


class Category(models.Model):
    """Category imported from the external WooCommerce source."""

    source_site = models.CharField(max_length=64, db_index=True, default="mehrdadgallery")
    source_category_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="شناسه دسته‌بندی در سایت منبع؛ خالی اگر در دسترس نباشد",
    )
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, allow_unicode=True, blank=True)
    source_url = models.URLField(max_length=1024, blank=True, default="")
    image_url = models.URLField(max_length=1024, blank=True, default="")
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    last_successful_sync_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "دسته‌بندی"
        verbose_name_plural = "دسته‌بندی‌ها"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["source_site", "source_category_id"],
                name="uniq_source_category",
                condition=~models.Q(source_category_id=""),
            ),
            models.UniqueConstraint(
                fields=["source_site", "slug"],
                name="uniq_source_category_slug",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug and self.name:
            self.slug = slugify(self.name, allow_unicode=True)[:255] or "category"
        super().save(*args, **kwargs)
