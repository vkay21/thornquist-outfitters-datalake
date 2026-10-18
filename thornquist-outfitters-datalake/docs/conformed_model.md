# Conformed Sales Model: how each schema conflict is resolved

(This complements Aish's `docs/schema_conflicts.md`, which holds the conflict analysis. This file shows where
the code resolves each conflict.)

| # | Conflict | POS | E-commerce | Customer extract | Conformed (`curated.fact_sales`) | Resolved in |
|---|---|---|---|---|---|---|
| C1 | Date format | `sale_date` mostly `YYYY-MM-DD`, 33 rows `DD/MM/YYYY` | `order_timestamp` ISO-8601 UTC | `signup_date` ISO | `sale_date` DATE (partition, string `yyyy-MM-dd`) | `raw_to_trusted_pos.py` (remediation) |
| C2 | Customer key | `cust_num` string, `0000000` = walk-in | `cust_ref` **integer** | `cust_num` string | `cust_num` STRING. Walk-in becomes NULL plus `is_walk_in` | POS and e-com jobs |
| C3 | Product taxonomy | `category` name, no SKU | `sku` with prefix APP/FOO/CAM/ACC, no category | — | `category` (POS name; e-com mapped from the SKU prefix), `sku` NULL for POS | `raw_to_trusted_ecommerce.py` |
| C4 | Region meaning | store location `region` | `shipping_region` (customer destination) | customer `region` (home) | `region` = where the sale happened or was shipped. `customer_home_region` kept separately | `trusted_to_curated.py` |
| C5 | Time zone and grain | date only, local store day | UTC timestamp: 01:20Z on 24 Aug is 21:20 on **23 Aug** in Toronto | — | `sale_date` = business day in America/Toronto. `sale_ts_utc` kept for e-com | `raw_to_trusted_ecommerce.py` |
| C6 | Grain | one row = one transaction = one item | one order = n items (nested array) | one row = one customer | one row = one sales **line**. `sales_line_id` = `POS-<txn>-1` / `WEB-<order>-<line>` | e-com job (`posexplode`) |
| C7 | Price and currency | `unit_price` float, CAD implied | `unit_price` float, `order_total` | — | `DECIMAL(10,2)` / `DECIMAL(12,2)`, explicit `currency = 'CAD'` | all jobs |
