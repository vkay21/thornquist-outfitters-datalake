# Integration agreement: final resources, S3 paths and schemas

Status: **proposed by Voke, 18 Oct 2026. Nothing new runs in AWS until both of us agree.**
Items marked ❓ need Aish's confirmation.

## 1. Existing resources (Aish's). These are reused, never recreated

| Resource | Name |
|---|---|
| Region | us-east-1 |
| Bucket | `thornquist-outfitters-datalake-672869298071` |
| Glue database (raw tables) | `thornquist_retail` |
| Crawlers | `thornquist-pos-crawler`, `thornquist-customer-crawler`, `thornquist-ecommerce-crawler` |
| Catalog tables | `pos_sales_2026_08_24_to_2026_08_30_csv`, `customer_extract_csv`, `ecommerce_orders_json` |
| Lambda (e-commerce) | `thornquist-ecommerce-ingestion` |
| Glue jobs | `thornquist-customer-landing-to-raw` (daily schedule, deactivated), `thornquist-pos-raw-to-trusted` |

## 2. New resources (Voke's): created by `deploy/deploy.sh`, removed by `deploy/teardown.sh`

| Resource | Name |
|---|---|
| Glue jobs | `thornquist-customer-raw-to-trusted`, `thornquist-ecommerce-raw-to-trusted`, `thornquist-trusted-to-curated`; `thornquist-pos-dq-gate` only if `POS_MODE=gate` |
| Glue workflow | `thornquist-pipeline`: customer → (POS ∥ e-commerce) → curated. Its weekly trigger is created **inactive** |
| Glue databases | `thornquist_trusted`, `thornquist_quarantine`, `thornquist_curated`. They are kept separate from `thornquist_retail` so Lake Formation can grant the analyst one whole database (curated) and nothing else |
| Athena workgroup | `thornquist-wg` (1 GB scan cutoff per query) |
| Monitoring | SNS `thornquist-pipeline-alerts`, EventBridge `thornquist-glue-job-failed`, alarms `thornquist-quarantine-spike-{pos,ecommerce}` |

`deploy.sh` now **runs nothing by default**. It also does **not** touch the bucket policy or lifecycle rules unless
`APPLY_GOVERNANCE=1` is set.

## 3. Final S3 layout (one bucket, zone = prefix)

| Zone | Path | Writer | Format |
|---|---|---|---|
| landing | `landing/{pos,ecommerce,customer}/` ❓ | Aish (upload, Lambda, Glue) | as delivered |
| raw | `raw/pos/` ❓ · `raw/ecommerce/` ❓ · `raw/customer/` ❓ | Aish | as delivered. E-commerce: JSON array or JSON Lines ❓ |
| trusted | `trusted/pos/` | Aish's job (or `thornquist-pos-dq-gate`) | Parquet |
| trusted | `trusted/ecommerce/` (partitioned `sale_date=`) | Voke | Parquet, one row per order line |
| trusted | `trusted/customer/` | Voke | Parquet |
| quarantine | `quarantine/{pos,ecommerce,customer}/batch_id=…/` | Voke | Parquet with `dq_failed_rules` |
| (reports) | `dq_reports/{source}/batch_id=…/dq_report.json` | Voke | JSON, one line |
| curated | `curated/fact_sales/channel=…/sale_date=…/`, `curated/dim_customer/`, `curated/agg_daily_sales/` | Voke | Parquet |
| (Athena results) | `athena-results/` | Athena | CSV |

If the raw paths differ from the ones above, override them without editing code:
`RAW_POS=s3://…/ RAW_ECOM=s3://…/ RAW_CUSTOMER=s3://…/ JSON_FORMAT=lines bash deploy/deploy.sh`

## 4. Trusted schemas (the contract the curated job reads)

**trusted/pos/ (Aish's job, as described):** the source columns `transaction_id, store_id, store_name, region,
sale_date (string yyyy-MM-dd), category, product_name, quantity, unit_price, payment_method, cust_num`. Exact
duplicates are removed with DISTINCT, and `0000000` is kept.
`trusted_to_curated.py` conforms this on read. It turns `sale_date` into a DATE, `0000000`/`0` into NULL plus
`is_walk_in`, and `cust_num` into a 6-digit string. It strips U+00A0, casts money to DECIMAL, flags orphan
customers, and keeps one row per `transaction_id`. Tested locally: the curated output is **identical** to the
gate path (1,687 lines, $337,945.57).

**trusted/ecommerce/:** `order_id, line_no, order_ts_utc, sale_date, channel, shipping_region, cust_num, sku,
category, product_name, quantity, unit_price, line_revenue, order_total, currency, is_orphan_customer,
extra_attributes, dq_flags, dq_remediations, dq_batch_id`

**trusted/customer/:** `cust_num, first_name, last_name, email, signup_date, loyalty_tier, home_region, dq_flags,
dq_remediations, dq_batch_id`

## 5. Decisions to agree

1. **POS raw→trusted: Aish's job or the DQ-gated job?** Both feed curated correctly. The difference is evidence
   for the 15-mark data-quality criterion:

   | | Aish's `thornquist-pos-raw-to-trusted` | `thornquist-pos-dq-gate` |
   |---|---|---|
   | Duplicate re-sends | Removed silently (DISTINCT) | 3 rows **quarantined**, visible in S3 and Athena |
   | Bad dates, prices, regions, IDs | Pass through or become NULL | Rejected to quarantine, rule IDs recorded |
   | Batch circuit breaker / alarm | — | Over 5 % rejected → nothing promoted, job fails, SNS alert |
   | DQ report | — | `dq_reports/pos/…` plus CloudWatch metrics |

   **Proposal:** run the gate job for POS (`POS_MODE=gate`). Keep Aish's job in the repo and the report as the
   first-iteration conformance step: it shows the date-normalisation design that the gate reuses. Then
   no POS quarantine evidence is missing.
2. **Two things worth checking in Aish's POS job** (reproduced locally with a simulation of it):
   * Spark's `trim()` removes ordinary spaces only, **not the non-breaking space (U+00A0)** in the sample. In
     the simulation, 13 rows kept it, which gives 27 distinct product names instead of 19. Fix:
     `F.trim(F.regexp_replace("product_name", " ", " "))`.
   * If the job reads through the crawler table, `cust_num` is typed `bigint`, so `0000000` becomes `0` and IDs
     lose their leading zeros. Fix: cast to string on read.
     (The curated job already corrects both, so nothing breaks either way.)
3. **Crawler targets.** Table names such as `pos_sales_2026_08_24_to_2026_08_30_csv` suggest each crawler points
   at a single **file**. Next week's file would then become a *new* table. Pointing each crawler at its
   **folder** (`raw/pos/` and so on) gives one stable table per source, with new files as partitions. That is
   the brief's "catalog stays accurate as new files arrive" requirement.
4. **Event-driven chain (optional).** The Lambda could end with
   `glue.start_workflow_run(Name='thornquist-pipeline')`.
5. **Demo split (8 min):** Aish covers zones, ingestion and the catalog (3 min). Voke covers the gate, curated
   layer, queries, governance and dashboard (4 min). 1 min for the wrap-up.

## 6. Agreed run order (one Learner Lab session)

1. Aish: confirm the ❓ items; fix the crawler targets if agreed; make sure all three files are in raw.
2. Voke: `POS_MODE=<agreed> bash deploy/deploy.sh` (creates everything, runs nothing).
3. Together: `aws glue start-workflow-run --name thornquist-pipeline`, then record it, following `docs/demo_runbook.md`.
4. `bash deploy/run_queries.sh` to save the evidence, then `bash deploy/teardown.sh`.
