# Data Quality Rule Catalogue

Implemented in `glue_jobs/lib/tq_dq.py` and the three `raw_to_trusted_*.py` jobs. A second, native
**Glue Data Quality** layer (`glue_dq_rulesets/*.dqdl`) re-checks the trusted tables.

## How the gate decides

| Outcome | Meaning | Where the row goes |
|---|---|---|
| **Remediate** | A deterministic, lossless fix (reformat a date, trim a space, replace a placeholder). Recorded in `dq_remediations`. | Continues to the rules |
| **REJECT** | The row breaks a rule the business cannot accept. | `quarantine/<source>/batch_id=<id>/` (Parquet, with `dq_failed_rules`) and **not** promoted |
| **FLAG** | The row is usable but suspect. | Promoted to `trusted/` with the rule ID in `dq_flags` (plus `is_orphan_customer`), and counted in the report |
| **Batch hold-back** | More than `max_reject_pct` (default **5 %**) of a batch is rejected, which points to a systemic fault (wrong file, broken export). | **Nothing** is promoted. The quarantine and report are still written, and the Glue job **fails**, which raises the CloudWatch alarm |

Each run writes `dq_reports/<source>/batch_id=<id>/dq_report.json`, which Athena can query as
`thornquist_quarantine.dq_reports`, and pushes counts to CloudWatch (`Thornquist/DataQuality`).

## Rules

| ID | Source | Dimension | Rule | Action | Seeded issue it catches |
|---|---|---|---|---|---|
| POS-01 | POS | Completeness | transaction_id, store_id, sale_date, product_name, quantity, unit_price are present | REJECT | – |
| POS-02 | POS | **Uniqueness** | transaction_id is unique (first copy wins) | REJECT | **3 terminal re-sends** |
| POS-03 | POS | Validity | sale_date parses (ISO or DD/MM/YYYY) and is plausible | REJECT | 33 DD/MM dates are **remediated**, not rejected |
| POS-04 | POS | **Range** | quantity is between 1 and 50 | REJECT | – |
| POS-05 | POS | **Range** | unit_price is between 0.01 and 5,000 | REJECT | placeholder 0.00 prices |
| POS-06 | POS | Validity | region, category and payment_method are in the reference domains | REJECT | – |
| POS-07 | POS | Validity | a non-walk-in cust_num is 6 digits | REJECT | – |
| POS-08 | POS | **Referential integrity** | cust_num exists in trusted/customers | FLAG | 0 in sample (the README expected some; see the report) |
| ECO-01 | E-com | Completeness | order_id, order_timestamp, cust_ref and ≥1 item are present | REJECT | – |
| ECO-02 | E-com | **Uniqueness** | order_id is unique (first copy wins) | REJECT | **5 webhook retries** |
| ECO-03 | E-com | Validity | order_timestamp is valid ISO-8601 and plausible | REJECT | – |
| ECO-04 | E-com | **Range** | every line has qty 1–50 and unit_price 0.01–5,000 | REJECT | – |
| ECO-05 | E-com | Validity | each SKU matches `(APP\|FOO\|CAM\|ACC)-9999` | REJECT | – |
| ECO-06 | E-com | Consistency | order_total = Σ(qty × unit_price) ± 0.01 | REJECT | – |
| ECO-07 | E-com | Validity | shipping_region and channel are in the reference domains | REJECT | – |
| ECO-08 | E-com | **Referential integrity** | cust_ref exists in trusted/customers | FLAG | **34 promoted orders (28 distinct IDs)** |
| CUS-01 | Customer | Completeness | cust_num is present and 6 digits | REJECT | – |
| CUS-02 | Customer | Uniqueness | cust_num is unique | REJECT | – |
| CUS-03 | Customer | Validity | signup_date is valid and not in the future | REJECT | – |
| CUS-04 | Customer | Validity | loyalty_tier is in {Standard, Silver, Gold} | REJECT | – |
| CUS-05 | Customer | Validity | email is well-formed | FLAG | – |
| CUS-06 | Customer | Validity | region is in the reference domain | FLAG | – |

### Remediations applied (sample batch)

| Remediation | Rows |
|---|---|
| `placeholder_to_null:cust_num_0000000`: walk-in placeholder becomes NULL plus `is_walk_in = true` | 185 |
| `date_reformatted:sale_date_ddmmyyyy`: DD/MM/YYYY becomes a DATE | 33 |
| `trimmed_whitespace:product_name`: leading spaces and a trailing NBSP (U+00A0) removed | 13 |

## Design decisions (for the report)

* **Why orphans are FLAGGED, not rejected.** The orders are real revenue. Quarantining them would understate
  online sales by 14 %. Customer-level analysis can exclude them with `NOT is_orphan_customer`, and Q8
  measures how exposed the business is.
* **Why the walk-in placeholder is remediated, not rejected.** `0000000` is a legitimate business state (an
  anonymous sale) encoded badly. Making it NULL stops a join from matching a fake "customer 0000000", and
  `is_walk_in` keeps the meaning.
* **Why DD/MM is remediated.** The pattern is unambiguous in this data (every day value is greater than 12) and
  comes from one terminal locale. An ambiguous date that is still unparseable would fail POS-03.
* **Why one bad line rejects the whole e-com order.** It keeps `order_total` consistent. Half an order in trusted
  is worse than a whole order in quarantine.
* **Duplicates.** Ordered by ingest sequence, the first copy is promoted and the rest are quarantined. This makes
  the job idempotent against retries and re-sends.

## Evidence

* `evidence/local_run/dq_report_*.json`: reports from the real sample batch
* `evidence/gate_demo/gate_demo_results.md`: a deliberately broken batch (tests/fixtures) where every REJECT rule
  fires, the batch is held back at 72.7 % rejected, a lenient re-run promotes 3 rows and quarantines 8, and
  schema-v2 JSON is handled
