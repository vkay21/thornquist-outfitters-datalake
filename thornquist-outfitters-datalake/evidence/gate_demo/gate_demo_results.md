# Quality-gate demonstration (deliberately broken input)

## POS bad batch - strict run

```json
{"source": "pos", "batch_id": "bad-batch-strict", "rows_checked": 11, "rows_promoted": 3, "rows_promoted_flagged": 1, "rows_quarantined": 8, "reject_pct": 72.73, "max_reject_pct": 5.0, "batch_decision": "HELD_BACK", "remediations_applied": {"date_reformatted:sale_date_ddmmyyyy": 1, "placeholder_to_null:cust_num_0000000": 1}, "rules": [{"rule_id": "POS-01", "name": "mandatory fields present", "dimension": "completeness", "action": "REJECT", "failed_rows": 1, "status": "FAIL", "description": "transaction_id, store_id, sale_date, product_name, quantity, unit_price must be non-empty."}, {"rule_id": "POS-02", "name": "transaction_id unique", "dimension": "uniqueness", "action": "REJECT", "failed_rows": 1, "status": "FAIL", "description": "Terminal batch re-sends: first copy promoted, repeats quarantined."}, {"rule_id": "POS-03", "name": "sale_date parseable and plausible", "dimension": "validity", "action": "REJECT", "failed_rows": 1, "status": "FAIL", "description": "After remediating DD/MM/YYYY, anything still unparseable or out of range is rejected."}, {"rule_id": "POS-04", "name": "quantity integer between 1 and 50", "dimension": "range", "action": "REJECT", "failed_rows": 1, "status": "FAIL", "description": "Returns are a separate feed; zero/negative or bulk quantities are suspicious."}, {"rule_id": "POS-05", "name": "unit_price between 0.01 and 5000", "dimension": "range", "action": "REJECT", "failed_rows": 1, "status": "FAIL", "description": "Catches placeholder 0.00 prices and decimal-shift errors."}, {"rule_id": "POS-06", "name": "region/category/payment in reference domains", "dimension": "validity", "action": "REJECT", "failed_rows": 2, "status": "FAIL", "description": "Curated aggregates group by these columns, so unknown values must not leak in."}, {"rule_id": "POS-07", "name": "cust_num well-formed", "dimension": "validity", "action": "REJECT", "failed_rows": 1, "status": "FAIL", "description": "Non-walk-in customer numbers must be 6 digits."}, {"rule_id": "POS-08", "name": "cust_num exists in customer master", "dimension": "referential_integrity", "action": "FLAG", "failed_rows": 2, "status": "WARN", "description": "Orphaned customer: revenue is real so the sale is promoted, flagged for steward follow-up."}]}
```

## POS bad batch - quarantined rows (lenient run)

|   transaction_id | sale_date   | product_name       |   quantity |   unit_price | region   | payment_method   | cust_num   | dq_failed_rules     |
|-----------------:|:------------|:-------------------|-----------:|-------------:|:---------|:-----------------|:-----------|:--------------------|
|           700001 | 2026-08-31  | Camp Stove         |          1 |        89.99 | Ontario  | VISA             | 100001     | ['POS-02']          |
|           700003 | 2026-13-45  | Trail Runner Low   |          1 |       120    | Ontario  | VISA             | 100002     | ['POS-03']          |
|           700004 | 2026-08-31  | 2-Person Tent      |         -2 |       299    | Ontario  | AMEX             | 100003     | ['POS-04']          |
|           700005 | 2026-08-31  | Dry Bag 20L        |          1 |         0    | Ontario  | VISA             | 100004     | ['POS-05']          |
|           700006 | 2026-08-31  | Sleeping Pad       |          1 |        59    | Nunavut  | VISA             | 100005     | ['POS-06']          |
|           700007 | 2026-08-31  | nan                |          1 |        79    | Ontario  | VISA             | 100006     | ['POS-01']          |
|           700008 | 2026-08-31  | Alpine Hiking Shoe |          1 |       189    | Quebec   | BITCOIN          | 100007     | ['POS-06']          |
|           700010 | 2026-08-31  | Down Vest          |          1 |       139    | Quebec   | VISA             | 12AB       | ['POS-07' 'POS-08'] |

## POS bad batch - promoted rows (lenient run)

|   transaction_id | sale_date           | product_name   |   cust_num | is_walk_in   | is_orphan_customer   | dq_flags   | dq_remediations                          |
|-----------------:|:--------------------|:---------------|-----------:|:-------------|:---------------------|:-----------|:-----------------------------------------|
|           700001 | 2026-08-31 00:00:00 | Camp Stove     |     100001 | False        | False                | []         | []                                       |
|           700002 | 2026-08-31 00:00:00 | Rain Shell     |        nan | True         | False                | []         | ['date_reformatted:sale_date_ddmmyyyy'   |
|                  |                     |                |            |              |                      |            |  'placeholder_to_null:cust_num_0000000'] |
|           700009 | 2026-08-31 00:00:00 | Camp Stove     |     999999 | False        | True                 | ['POS-08'] | []                                       |

## E-commerce schema v2 - promoted lines (new fields kept in extra_attributes)

|   order_id | channel   | sku      | category   |   quantity |   line_revenue | extra_attributes                         |
|-----------:|:----------|:---------|:-----------|-----------:|---------------:|:-----------------------------------------|
|     910001 | app       | CAM-1111 | Camping    |          1 |             80 | {"gift_wrap":true,"promo_code":"FALL10"} |

## E-commerce schema v2 - quarantined orders

|   order_id | order_timestamp      |   order_total | dq_failed_rules     |
|-----------:|:---------------------|--------------:|:--------------------|
|     910003 | not-a-date           |            10 | ['ECO-03' 'ECO-05'] |
|     910002 | 2026-08-31T16:30:00Z |           150 | ['ECO-06']          |

## AWS bad-batch test — verified October 21, 2026

- **Glue job:** `thornquist-pos-dq-gate`
- **AWS Region:** `us-east-1`
- **Batch ID:** `20261021T162228Z`
- **Input:** `s3://thornquist-outfitters-datalake-672869298071/raw/pos_badbatch/`
- **Glue run ID:** `jr_7e2848e7633f07c133edbb455e1c47a219c87c92c9a48efea4409367a29ba6d7`
- **Job status:** `FAILED` — expected for this rejection test
- **Rows checked:** 11
- **Rows quarantined:** 8
- **Rejection rate:** 72.73%
- **Maximum allowed rejection rate:** 5%
- **Batch decision:** `HELD_BACK`
- **Error:** `BatchRejected: 72.73% rejected > threshold 5.0% - nothing promoted`

The JSON report and quarantine Parquet files were verified under `tmp/badbatch-test/`. The test used isolated temporary output paths rather than the normal trusted POS or curated paths.
