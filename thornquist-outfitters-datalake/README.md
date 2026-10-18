# Thornquist Outfitters: Governed Data Lake

CCGC 5506 Mid-Term Project 1 · Humber · Fall 2026

A first-generation, serverless data lake for a fictional multi-channel outdoor retailer. It ingests store
POS CSVs, storefront order JSON and a legacy customer flat file. It reconciles them into one conformed sales
model behind an automated data-quality gate, and exposes a partitioned Parquet layer to Athena and a
dashboard. Everything is built to run inside an **AWS Academy Learner Lab** (single `LabRole`, 4-hour
sessions, budget cap, us-east-1).

```
 POS CSV ──(scripted upload)──┐
 E-com JSON ──(S3 event → Lambda)──┼─▶ landing/ ─▶ raw/ ──▶ [Glue: DQ gate] ──▶ trusted/ ──▶ [Glue: conform + partition] ──▶ curated/ ──▶ Athena ──▶ notebook dashboard
 Customer extract ──(scheduled Glue)┘   (immutable)      │                              (Parquet, channel/sale_date)   ▲ Lake Formation
                                                          └─▶ quarantine/ + dq_reports/ ──▶ CloudWatch metrics + EventBridge → SNS alerts
```

## Repository layout

| Path | Owner | Contents |
|---|---|---|
| `infra/`, `ingestion/` | Aish | S3 zone setup, three ingestion mechanisms (upload script, Lambda, scheduled Glue), crawlers |
| `docs/schema_conflicts.md` | Aish | Schema-conflict analysis |
| `glue_jobs/raw_to_trusted_*.py` | Voke | DQ gate jobs (customer, POS, e-commerce) |
| `glue_jobs/trusted_to_curated.py` | Voke | Conformed `fact_sales`, `dim_customer`, `agg_daily_sales` |
| `glue_jobs/lib/` | Voke | Shared helpers + the rule engine (`tq_dq.py`) |
| `data_quality/` | Voke | Rule catalogue (`dq_rules.md`) + native Glue Data Quality rulesets (`.dqdl`) |
| `sql/ddl/` | Voke | Athena DDL: manually curated tables with partition projection |
| `sql/analytics/` | Voke | 8 business-question queries |
| `sql/benchmark/` | Voke | CSV vs Parquet / partitioned benchmark (stretch goal) |
| `governance/` | Voke | IAM policy designs, bucket policies, Lake Formation grants, lifecycle, RACI, cost note |
| `dashboard/` | Voke | Notebook dashboard (Athena or local) + exported figures |
| `deploy/` | Voke | `deploy.sh`, `run_queries.sh`, `teardown.sh` (CloudShell) |
| `local/`, `tests/` | Voke | Run the whole pipeline on a laptop, plus a broken-batch demo of the gate |
| `evidence/` | both | Query outputs, DQ reports, screenshots, recordings |

## Reproduce from a fresh Learner Lab session

**0. Start the lab** and open **CloudShell** (region `us-east-1`). Then run
`git clone https://github.com/vkay21/thornquist-outfitters-datalake.git && cd thornquist-outfitters-datalake`

**1. Zones and ingestion (Aish's part).** Follow `ingestion/README.md`. Afterwards the three sample files sit
in `raw/pos/`, `raw/ecommerce/` and `raw/customer/`, and the raw crawlers have run.

**2. Quality gate, curated layer, monitoring and Athena tables**
```bash
# bucket defaults to thornquist-outfitters-datalake-672869298071
export ALERT_EMAIL=you@example.com          # optional: SNS email on job failure
bash deploy/deploy.sh                       # jobs, workflow thornquist-pipeline, alarms, workgroup, tables; runs nothing
#   POS_MODE=gate        use thornquist-pos-dq-gate instead of Aish's thornquist-pos-raw-to-trusted
#   APPLY_GOVERNANCE=1   apply bucket policy + lifecycle (replaces existing ones)
aws glue start-workflow-run --name thornquist-pipeline
```
Watch **Glue → Workflows → thornquist-pipeline → History**. A run takes about 5–8 minutes:
`customer → (POS ∥ e-commerce) → curated`.

**3. Queries and evidence**
```bash
bash deploy/run_queries.sh              # runs sql/analytics/*.sql, saves CSVs to evidence/athena_run/
```

**4. Governance (optional in a demo session)**
```bash
bash governance/lakeformation/lf_grants.sh
```

**5. Dashboard.** Open `dashboard/thornquist_dashboard.ipynb` with `TQ_MODE=athena` and `BUCKET` set.

**6. Before logging off:** `bash deploy/teardown.sh`. The bucket is kept unless `DELETE_BUCKET=1`.
Nothing here is always-on, but deleting the jobs and workgroup keeps the account tidy across resets.

## Run it locally (no AWS): used for development and the evidence in `evidence/local_run`
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-local.txt          # needs Java 17+
python local/run_local.py --sample-dir <path>/Project1_Thornquist_Outfitters_SampleData [--pos-mode aish|gate]
python tests/run_gate_demo.py                  # deliberately broken batch → quarantine + held-back batch
TQ_MODE=local jupyter nbconvert --execute --to notebook --inplace dashboard/thornquist_dashboard.ipynb
```
The Glue scripts run **unchanged** in both places. `glue_jobs/lib/tq_common.py` detects Glue and switches
argument parsing, I/O and CloudWatch publishing accordingly.

## Results on the provided sample (week of 24–30 Aug 2026)

| Source | Rows in | Promoted | Flagged | Quarantined | Remediated |
|---|---|---|---|---|---|
| Customer extract | 400 | 400 | 0 | 0 | 0 |
| POS | 1,051 | 1,048 | 0 | **3** duplicate re-sends | 185 walk-in placeholders, 33 DD/MM dates, 13 whitespace names |
| E-commerce | 265 orders | 260 orders, 639 lines | **34** orphan customers | **5** webhook duplicates | — |

Curated `fact_sales` holds 1,687 lines and $337,946 of revenue. Answers to the eight business questions are
in `evidence/local_run/query_results.md`.

## Key design choices
* **Four zones plus quarantine.** Promotion rules are in `docs/zones_and_promotion.md`. Raw is immutable
  (enforced by the bucket policy).
* **Row-level quarantine plus a batch circuit-breaker** (>5 % rejected means nothing is promoted and the job fails).
* **Partition projection** on the curated tables, so no crawler is needed downstream of trusted and new days
  are queryable immediately.
* **Learner Lab IAM.** The policies are designed for four separate roles. Enforcement in the lab uses the bucket
  policy, Lake Formation and Athena workgroup controls. See `governance/README.md`.
