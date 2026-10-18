# Zones and Promotion Rules

| Zone | Prefix | Format | Who writes | Promotion rule into the NEXT zone |
|---|---|---|---|---|
| Landing | `landing/<source>/` | As delivered (CSV / JSON / flat file) | Ingestion (upload script, Lambda, scheduled Glue) | File is complete (no partial uploads: the object exists and size > 0), arrives through a known source pattern, and its name matches the source convention. It is copied **unchanged** to raw under `ingest_date=YYYY-MM-DD/`, then expires from landing after 7 days. |
| Raw | `raw/<source>/ingest_date=…/` | As delivered, **immutable** | Ingestion only | Glue DQ gate job: remediation, then rules, then the batch threshold (≤ 5 % rejected). Passing rows are typed and conformed to the per-source trusted schema. |
| Quarantine | `quarantine/<source>/batch_id=…/` | Parquet with `dq_failed_rules` | Glue DQ gate | Never promoted automatically. A data steward fixes the data at source and re-sends; the next batch is gated again. Expires after 90 days. |
| Trusted | `trusted/<entity>/sale_date=…/` | Parquet (Snappy), typed, one schema per source | Glue DQ gate | Every row passed all REJECT rules. FLAG rules are recorded in `dq_flags`. Runs only after all three sources have succeeded (workflow conditional trigger). |
| Curated | `curated/fact_sales/channel=…/sale_date=…/` | Parquet, conformed and query-shaped | Glue `trusted_to_curated` only | End of the line: read by Athena under Lake Formation grants. |

**Why these boundaries**
* **Landing / raw:** landing is a scratch inbox that anyone in the ingestion path can write to. Raw is the
  audited, replayable copy. Any downstream bug can be fixed by re-running from raw.
* **Raw / trusted:** the quality gate is the boundary. Nothing reaches trusted without passing the rules, so
  trusted is the first zone a data steward can vouch for.
* **Trusted / curated:** trusted is source-shaped (one table per system). Curated is question-shaped: one
  conformed fact, denormalised segment attributes, partitioned for the query patterns, and governed by Lake
  Formation for analysts.
