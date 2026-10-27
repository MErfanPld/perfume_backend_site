"""
Management command: import a small sample of products from Mehrdad Gallery
or from a local HTML fixture when the remote source is unreachable.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from products.services.importer import (
    SourceUnavailableError,
    run_import_from_fixture,
    run_import_from_url,
)


class Command(BaseCommand):
    help = (
        "Import a limited sample of products from the configured source website "
        "or from a local HTML fixture. Exact stock quantities are never invented."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--url",
            default=None,
            help="Source listing URL (default: shop page of SOURCE_BASE_URL)",
        )
        parser.add_argument(
            "--fixture",
            type=str,
            default=None,
            help="Path to a local HTML fixture file (used when live fetch is impossible)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help=f"Max products to import (default: {getattr(settings, 'IMPORT_DEFAULT_LIMIT', 5)})",
        )
        parser.add_argument(
            "--source-site",
            default=None,
            help="Source site identifier stored on Product (default: SOURCE_SITE_ID)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse only; do not write to the database",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        if limit is None:
            limit = getattr(settings, "IMPORT_DEFAULT_LIMIT", 5)
        source_site = options["source_site"] or getattr(
            settings, "SOURCE_SITE_ID", "mehrdadgallery"
        )
        fixture = options["fixture"]
        url = options["url"]
        dry_run = options["dry_run"]

        if fixture:
            path = Path(fixture)
            if not path.is_file():
                raise CommandError(f"Fixture file not found: {path}")
            self.stdout.write(self.style.WARNING(f"Using local fixture: {path}"))
            if dry_run:
                from products.services.importer import load_fixture
                from products.services.parser import parse_listing_html

                html = load_fixture(path)
                products = parse_listing_html(
                    html, base_url=getattr(settings, "SOURCE_BASE_URL", "https://mehrdadgallery.com")
                )
                self.stdout.write(f"Parsed {len(products)} product(s) (dry-run, limit={limit}):")
                for p in products[:limit]:
                    self.stdout.write(
                        f"  - id={p.source_product_id} name={p.name[:50]!r} "
                        f"avail={p.availability} reg={p.regular_price} sale={p.sale_price}"
                    )
                return

            stats = run_import_from_fixture(
                path, source_site=source_site, limit=limit
            )
        else:
            if not url:
                base = getattr(settings, "SOURCE_BASE_URL", "https://mehrdadgallery.com")
                url = f"{base.rstrip('/')}/shop/"
            self.stdout.write(f"Fetching: {url}")
            try:
                if dry_run:
                    from products.services.importer import fetch_html
                    from products.services.parser import parse_listing_html

                    html = fetch_html(url)
                    products = parse_listing_html(
                        html,
                        base_url=getattr(settings, "SOURCE_BASE_URL", "https://mehrdadgallery.com"),
                    )
                    self.stdout.write(f"Parsed {len(products)} product(s) (dry-run, limit={limit}):")
                    for p in products[:limit]:
                        self.stdout.write(
                            f"  - id={p.source_product_id} name={p.name[:50]!r} "
                            f"avail={p.availability} reg={p.regular_price} sale={p.sale_price}"
                        )
                    return

                stats = run_import_from_url(url, source_site=source_site, limit=limit)
            except SourceUnavailableError as exc:
                raise CommandError(
                    f"{exc}\n"
                    "The remote source is unreachable from this environment. "
                    "Re-run with --fixture path/to/listing.html to test the parser "
                    "against a saved HTML sample."
                ) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Import finished: created={stats['created']} "
                f"updated={stats['updated']} skipped={stats['skipped']} "
                f"errors={stats['errors']}"
            )
        )
