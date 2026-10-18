# Evidence and recording checklist (one Learner Lab session, about 60–90 min)

Record each step with the screen recorder; keep clips short (20–60 s). Save stills to `evidence/screenshots/`.

| # | Do this | Capture |
|---|---|---|
| 1 | `bash deploy/deploy.sh` in CloudShell | The terminal output: jobs, workflow, alarms, `SUCCEEDED` DDL |
| 2 | Glue → Workflows → `tq-pipeline` → Run → graph view | **Clip:** the graph turning green, customer → pos ∥ ecommerce → curated |
| 3 | Glue → Jobs → `tq-raw-to-trusted-ecommerce` → run → Output logs | The `[dq]` lines: ECO-02 FAIL 5, ECO-08 WARN 35 |
| 4 | S3 → `quarantine/pos/batch_id=…/` and `quarantine/ecommerce/` | **Quarantined batch visible**, next to `trusted/` (the promoted version) |
| 5 | S3 → `dq_reports/…/dq_report.json` → Open | The JSON report |
| 6 | **Bad batch:** upload `tests/fixtures/pos_sales_bad_batch.csv` to `raw/pos_badbatch/`, then run `tq-raw-to-trusted-pos` with job parameter `--raw_path s3://$BUCKET/raw/pos_badbatch/` | **Clip:** the run **FAILS** with `BatchRejected 72.73%`, and the SNS email / EventBridge rule fires |
| 7 | Athena (workgroup `thornquist-wg`): run `SELECT * FROM thornquist_quarantine.dq_reports` | The DQ history table |
| 8 | `bash deploy/run_queries.sh` (or paste the q01–q08 files into the Athena editor) | Each result plus "Data scanned" |
| 9 | Benchmark: `sql/benchmark/benchmark_csv_vs_parquet.sql` | Bytes scanned A vs B vs C → `docs/benchmark_results.md` |
| 10 | `bash governance/lakeformation/lf_grants.sh` → Lake Formation → Data permissions | The grants list, the PII column exclusion and the `ontario_only` data filter |
| 11 | S3 → bucket → Permissions | The bucket policy and lifecycle rules |
| 12 | CloudWatch → Alarms and Metrics → `Thornquist/DataQuality` | The `rows_quarantined` metric |
| 13 | Dashboard notebook in Athena mode (or show the local-mode figures) | The figures |
| 14 | `bash deploy/teardown.sh` | Proof of cleanup |

**Service-availability fallbacks (worth marks):**
- QuickSight is missing, so we use the notebook.
- If SNS email is blocked, the EventBridge rule still shows in the console.
- If the Lake Formation grant to a non-existent role is rejected, show `lf_permissions.json` as the design and
  the grant to `voclabs`.
- If Glue 4.0 is unavailable, use `GLUE_VERSION=5.0`.
