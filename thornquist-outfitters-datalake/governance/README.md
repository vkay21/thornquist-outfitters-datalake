# Governance Package

Learner Lab gives every student one pre-built role (`LabRole` for services and `voclabs` for the console) and
blocks creating IAM roles, users and, usually, policies. So this package has **two layers**:

1. **Design artifacts**: the least-privilege policies we *would* attach to four separate roles in a real
   account. They are reviewed, validated JSON, but cannot be deployed in the lab.
2. **Verified live controls and deployment limitations**: the Athena workgroup has a configured result
   location and a 1 GiB per-query scan limit, and S3 Block Public Access is enabled. At the last verification,
   no S3 bucket policy or lifecycle configuration was attached. Lake Formation permissions and administrator
   settings could not be inspected because the current `voclabs` role was denied access to the relevant APIs.
   Do not describe the policy and grant files below as deployed controls unless they are verified in AWS.

| File | Deployable in Learner Lab? | Purpose |
|---|---|---|
| `iam/tq-ingestion-policy.json` | ✗ (design) | Lambda and upload role: write `landing/`, promote to `raw/`, start crawlers and jobs. Cannot read trusted or curated. |
| `iam/tq-glue-etl-policy.json` | ✗ (design) | Glue role: read `raw/`, write `trusted/`, `quarantine/`, `curated/`. Catalog limited to `thornquist_*`. CloudWatch metrics limited to the `Thornquist/*` namespace. |
| `iam/tq-analyst-policy.json` | ✗ (design) | Athena in the `thornquist-analyst-wg` workgroup only, its own results prefix, and an explicit deny on upstream zones. Table, column and row visibility is decided by Lake Formation. |
| `s3/bucket-policy-production.json` | ✗ (design) | Zone isolation by `aws:PrincipalArn` for the four `tq-*` roles |
| `s3/bucket-policy-learner-lab.json` | Design only; not attached at last verification | Proposed zone controls and TLS-only access. Review carefully before deployment; do not assume the raw zone is immutable. |
| `s3/lifecycle-policy.json` | Design only; not configured at last verification | Proposed storage tiering and expiry by zone. Actual transitions and expiration are not active unless the configuration is deployed. |
| `lakeformation/lf_grants.sh` / `lf_permissions.json` | Not live-verified | Proposed curated-data, column, and row-level grants. The current console role could not inspect Lake Formation permissions, and the script must not be run blindly. |

### Least privilege: how close the lab gets

* **Ingestion vs ETL separation** cannot be fully enforced using the lab's shared pre-created service role.
  The proposed bucket policy describes intended zone isolation, but it was not attached at last verification.
* **Analyst confinement** is a target control, not a verified live permission boundary. Do not claim that
  `IAMAllowedPrincipals` has been revoked or that column and row filters are active without evidence from AWS.
* **Resource scoping everywhere.** No policy uses `"Resource": "*"` for S3. Glue access is limited to
  `thornquist_*` databases, and `PutMetricData` is limited by a namespace condition.
* **Athena workgroup** `thornquist-wg` enforces its own result location and a 1 GB per-query scan cutoff, which
  guards against cost blowouts. It is created by `deploy/deploy.sh`.

> ⚠️ Lab safety: the Learner Lab restricts some IAM and Lake Formation operations. The proposed bucket
> policy has not been attached. Do not attach it or run the Lake Formation grant script without reviewing the
> policy, its effects on cleanup, and the permissions available to the current lab role.

## Intended RACI and access model (not live-verified)

R = Responsible (does the work) · A = Accountable (owns it) · C = Consulted · I = Informed. The access
column shows the permission each persona actually gets.

| Zone / asset | Platform admin (voclabs) | Ingestion role (Lambda / upload) | Glue ETL role | Data steward | Analyst | Regional manager |
|---|---|---|---|---|---|---|
| `landing/` | A · manage | **R** · write | read (promote) | I · no access | no access | no access |
| `raw/` (intended immutable; enforcement not deployed) | A · manage | **R** · write once | read | C · no access | no access | no access |
| `trusted/` | A | no access | **R** · read/write | C · read | no access | no access |
| `quarantine/` + `dq_reports/` | A | no access | **R** · write | **R** · read, triage | I (Q8 summary only) | no access |
| `curated/fact_sales` | A | no access | **R** · write | C · read | **read** (all columns) | **read, Ontario rows only, no cust_num** |
| `curated/dim_customer` | A | no access | **R** · write | read incl. PII | read **without** name/email | no access |
| DQ rules & thresholds | I | I | R (implements) | **A** (owns rules) | C | I |
| Bucket policy / LF grants | **A/R** | I | I | C | I | I |

## Cost and performance note (curated layer)

* **Parquet + Snappy.** The columnar format means a query that touches 2 of 26 columns reads about 8 % of the
  bytes. Snappy is fast to decompress, and Athena bills on compressed bytes scanned.
* **Partitioned by `channel` then `sale_date`.** Almost every business question filters on a date range and
  often on channel. One day of POS lands as exactly one partition, so a re-run overwrites only that day (dynamic
  partition overwrite keeps re-runs idempotent). **Partition projection** removes crawler runs and
  `MSCK REPAIR` (crawlers cost DPU-minutes per run).
* **File sizing.** Each partition is written as one file to avoid the small-files problem: Athena pays per S3
  request and per file opened. At Thornquist's real scale (40 stores) a day would still be well under 128 MB,
  so `sale_month` partitions plus compaction would be the next step if the partition count grows past
  ~10k.
* **Lifecycle (proposed; not deployed).** The following transitions describe the intended lifecycle policy, not active S3 configuration. Curated partitions would move to **S3 Standard-IA after 90 days**: analysts mostly query the
  current quarter and IA costs about 45 % less, while 90 days is past IA's 30-day minimum and covers quarter
  close. They move to **Glacier Instant Retrieval after 365 days**, which stays queryable by Athena with
  millisecond access for year-over-year comparisons. Raw moves to Glacier Flexible after 180 days because it is
  only needed for replay or audit. Landing, tmp and Athena results expire within days.
* **No always-on compute.** Glue jobs run on 2 DPUs (G.1X) with a 10-minute timeout, and Athena is pay per TB
  scanned. Running the whole pipeline weekly on this data costs cents. A Redshift cluster or an always-on EMR
  cluster would cost dollars per hour even when idle.
