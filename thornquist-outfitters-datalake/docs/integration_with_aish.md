# Integration contract: Aish's half ↔ Voke's half

My jobs read from the raw zone and need only these facts from the ingestion side. Fill in the
right-hand column once Aish confirms.

| Item | Assumed in my code (`deploy/deploy.sh` defaults) | Aish's actual value |
|---|---|---|
| Bucket | `$BUCKET` (single bucket, zone = prefix) | |
| Region | us-east-1 | |
| Raw POS path | `s3://$BUCKET/raw/pos/` (any sub-folders, CSV with header) | |
| Raw e-commerce path | `s3://$BUCKET/raw/ecommerce/` (JSON array per file; set `--json_format lines` if her Lambda writes JSONL) | |
| Raw customer path | `s3://$BUCKET/raw/customer/` (CSV with header) | |
| Glue databases | `thornquist_raw` (hers), `thornquist_trusted`, `thornquist_quarantine`, `thornquist_curated` | |
| POS raw→trusted | Hers **or** `tq-raw-to-trusted-pos` (mine, with DQ gate). Keep ONE. If hers: `SKIP_POS=1 bash deploy/deploy.sh` and her output must land at `trusted/pos_sales/` with the column names in `glue_jobs/raw_to_trusted_pos.py` (final `select`) | |
| Lambda | Copies landing→raw only. Optionally ends with `glue.start_workflow_run(Name='tq-pipeline')` to make the whole chain event-driven | |

### Decisions to agree on
1. **POS job:** merge her conformance logic with my gate (recommended: keep my job, which already handles
   DD/MM dates, the `0000000` placeholder, NBSP trimming and duplicates, and credit her schema-conflict
   analysis in the report), or keep hers and pipe her output through my rules.
2. **Raw table for customer `cust_num`:** her crawler may infer `bigint`. That is a good example for the
   "manually curated table" requirement (we already have one on the curated side, so either works).
3. **Who presents what in the 8-minute demo:** suggested split: Aish covers zones, ingestion and the catalog
   (3 min); Voke covers the DQ gate, curated layer, queries, dashboard and governance (4 min); 1 min for the
   wrap-up together.
