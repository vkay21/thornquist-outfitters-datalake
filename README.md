# Thornquist Outfitters: Governed Data Lake

**CCGC 5506 — Mid-Term Project 1 | Humber College | Fall 2026**

Thornquist Outfitters is a serverless data lake project for a fictional multi-channel outdoor retailer. It brings together point-of-sale (POS) CSV files, e-commerce order JSON, and a legacy customer extract. The pipeline organizes source data into lake zones, applies data-quality checks, standardizes records, and prepares curated Parquet data for Amazon Athena queries and dashboard reporting.

The project is designed for an **AWS Academy Learner Lab** using the `us-east-1` region and the lab-provided `LabRole`. Learner Lab sessions are time-limited, so start the lab before running AWS commands.

## Architecture overview

```text
POS CSV ────────────────┐
E-commerce JSON ────────┼──> Landing ──> Raw ──> Data-quality checks ──> Trusted
Customer extract ──────┘                            │                       │
                                                    └──> Quarantine         v
                                                                      Curated Parquet
                                                                            │
                                                                            v
                                                                      Athena queries
                                                                            │
                                                                            v
                                                                      Dashboard/reporting

Monitoring and governance support the pipeline. Some governance controls are documented as
design artifacts and must be checked in the target Learner Lab before being applied.
```

## Repository layout

| Path | Purpose |
|---|---|
| `infra/` | Infrastructure setup resources and configuration |
| `ingestion/` | Source-data ingestion scripts and instructions |
| `glue_jobs/` | AWS Glue ETL and data-quality job scripts, including curated-layer processing |
| `data_quality/` | Data-quality rule catalogue and rulesets |
| `sql/ddl/` | Athena database and table definitions |
| `sql/analytics/` | SQL queries for the project's business questions |
| `sql/benchmark/` | CSV/Parquet and partitioning benchmark materials |
| `governance/` | IAM, bucket policy, Lake Formation, lifecycle, cost, and responsibility documentation |
| `deploy/` | Deployment, query-running, and teardown scripts |
| `local/` | Local pipeline execution tools |
| `tests/` | Data-quality gate and pipeline tests |
| `dashboard/` | Dashboard notebook and exported visualizations |
| `docs/` | Architecture, schema-conflict analysis, and technical documentation |
| `evidence/` | Query outputs, quality reports, screenshots, and other project evidence |

## AWS deployment and reproduction

These instructions describe the intended deployment workflow. Confirm resource names, permissions, and the current contents of the scripts before running them in a fresh Learner Lab.

### 1. Start the Learner Lab

1. Start your AWS Academy Learner Lab.
2. Open **CloudShell** and select **US East (N. Virginia) — `us-east-1`**.
3. Clone the repository:

```bash
git clone https://github.com/vkay21/thornquist-outfitters-datalake.git
cd thornquist-outfitters-datalake
```

### 2. Configure ingestion and source data

Follow [`ingestion/README.md`](ingestion/README.md) for the source-data and ingestion setup. The project includes mechanisms for POS CSV upload, event-triggered e-commerce JSON ingestion, and customer extract ingestion.

Before proceeding, confirm that the expected input files and S3 prefixes match the configuration in the scripts. Resource names and paths must be consistent across ingestion, Glue jobs, crawlers, and Athena definitions.

### 3. Deploy pipeline resources

Review `deploy/deploy.sh` before executing it. The script is intended to configure the project's Glue jobs and workflow, monitoring resources, Athena workgroup, and table definitions.

```bash
# Optional: configure an email destination if the deployment script supports it
export ALERT_EMAIL=you@example.com

bash deploy/deploy.sh
```

The deployment script comments describe optional settings, including `POS_MODE=gate` and `APPLY_GOVERNANCE=1`. **Do not enable `APPLY_GOVERNANCE=1` without reviewing the current bucket policy, lifecycle configuration, permissions, and script behavior**, because applying it may replace existing settings.

### 4. Run and monitor the Glue workflow

If the workflow is configured and the required permissions are available, start it with:

```bash
aws glue start-workflow-run --name thornquist-pipeline
```

Monitor **AWS Glue → Workflows → `thornquist-pipeline` → History**. Check the status and logs of each job rather than assuming that starting the workflow means every stage succeeded. The intended flow is customer processing alongside POS and e-commerce processing, followed by curated-layer generation.

### 5. Run Athena queries

After the curated tables have been created and populated, run the query script:

```bash
bash deploy/run_queries.sh
```

The script is intended to run the analytics SQL and save outputs under `evidence/athena_run/`. Verify the output path and successful query results after execution.

### 6. Open the dashboard

Open `dashboard/thornquist_dashboard.ipynb` in a compatible Jupyter environment. The notebook supports local mode and may support Athena mode when the AWS configuration, permissions, and dependencies are available. Check the notebook configuration before selecting a mode.

### 7. Clean up AWS resources

Do not run `deploy/teardown.sh` before the demonstration, evidence capture, or submission. It may delete project resources required for the live demo. Only perform cleanup after the team has saved all required evidence and no longer needs the environment.

## Run locally

Local execution is useful for development and for reproducing the local evidence without deploying AWS resources. It requires Python dependencies and Java 17 or later.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-local.txt

python local/run_local.py \
  --sample-dir /path/to/Project1_Thornquist_Outfitters_SampleData \
  --pos-mode aish

python tests/run_gate_demo.py
```

Replace `/path/to/Project1_Thornquist_Outfitters_SampleData` with the actual directory containing the supplied sample files. Use the `--pos-mode` option supported by the local runner if you need to test a different POS processing mode.

To execute the dashboard notebook in local mode, use the notebook instructions and dependencies documented in the repository. Do not overwrite the notebook unless you intend to save the executed output.

## Data quality and validation

The project includes checks for duplicate records, inconsistent dates, placeholder customer identifiers, whitespace in product names, orphan customer references, and excessive batch rejection. Failed records can be quarantined with quality reports. The intended batch circuit-breaker rejects a batch when the rejected proportion exceeds the configured threshold.

Recorded sample-data checks include:

| Source | Input | Promoted | Quarantined / flagged | Notes |
|---|---:|---:|---:|---|
| Customer extract | 400 rows | 400 rows | 0 quarantined | All checked customer rows promoted in the recorded run |
| POS | 1,051 rows | 1,048 rows | 3 quarantined | Duplicate re-sends; date standardization and walk-in placeholder handling also recorded |
| E-commerce | 265 orders | 260 orders | 5 duplicate orders quarantined | Orphan customer references were flagged and require careful interpretation |

These are recorded data-quality results; they should not be interpreted as proof that every stage has been successfully deployed and rerun in every AWS environment.

## Analytics results

The latest recorded Athena results for the week of **August 24–30, 2026** were:

| Metric | Latest recorded Athena result |
|---|---:|
| Curated sales lines | 1,669 |
| Revenue | $333,411.72 |
| Store revenue | $214,561.78 |
| Online revenue | $118,849.94 |
| Store sales lines | 1,048 |
| Online sales lines | 621 |

The local evidence has previously shown different totals from Athena. Treat local and AWS results as separate execution results until the difference has been reconciled against the source files and transformation logic. See `evidence/local_run/query_results.md` for the documented local query outputs and the technical report for the analysis of the discrepancy.

## Governance, security, and cost

- The project is intended to run within the permissions and resource limits of an AWS Academy Learner Lab.
- Use the lab-provided role (`LabRole`) and least-privilege permissions appropriate to the environment.
- Review governance artifacts before applying them. A policy or grant file in the repository does not by itself mean that the control is deployed.
- The S3 bucket policy and Lake Formation grants have been documented as not fully deployed or verified in this Learner Lab. Confirm the live configuration in AWS before describing these controls as operational.
- Monitor Glue runs, CloudWatch alarms, Athena data scanned, and S3 storage. Stop or remove resources only when they are no longer needed and the evidence has been saved.

## Project deliverables

This repository supports the project deliverables, including:

- Infrastructure and ingestion scripts
- Glue processing and data-quality code
- Athena DDL and analytics queries
- Architecture and schema-conflict documentation
- Technical report, dashboard, and evidence artifacts

For grading, use the latest files in the repository and verify that the technical report, screenshots/recordings, and dashboard outputs correspond to the execution results being presented.

## Repository

GitHub: [vkay21/thornquist-outfitters-datalake](https://github.com/vkay21/thornquist-outfitters-datalake)
