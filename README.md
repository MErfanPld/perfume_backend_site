# Perfume Backend Site — Phase 2 Prototype

Minimal Django prototype for importing perfume product listings from an external WooCommerce source (Mehrdad Gallery research target).

## Important limitations

- Live HTTP requests to `https://mehrdadgallery.com/` timed out from the development environment used for this phase.
- The parser and import command are therefore tested against a **clearly labeled local HTML fixture** (`products/fixtures/mehrdadgallery_shop_sample.html`).
- Exact stock quantities are **not** exposed in the observed public listing data; `stock_quantity` is always stored as `null` unless an explicit numeric quantity appears in the source HTML.
- Only binary availability (`in_stock` / `out_of_stock` / `unknown`) is synchronized from public pages.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py test products
```

## Import from fixture (recommended while live access is blocked)

```bash
python manage.py import_source_products --fixture products/fixtures/mehrdadgallery_shop_sample.html --limit 5
```

## Import from live URL (when the source is reachable)

```bash
python manage.py import_source_products --url https://mehrdadgallery.com/shop/ --limit 5
```

If the remote host is unreachable the command exits with a clear error and does not invent data.

## Model

`products.Product` stores:

- `source_site` + `source_product_id` (unique together)
- name, product_url, regular_price, sale_price, currency
- availability, stock_quantity (nullable), image_url
- source_last_seen_at, last_successful_sync_at, raw_data

## Next phase

Awaiting approval before any storefront, cart, checkout, or payment features are added.
