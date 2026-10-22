# S3 Governance Status

Bucket: `thornquist-outfitters-datalake-672869298071`
Region: `us-east-1`
Verification date: 22 October 2026

## Deployed control

The current bucket policy is saved in `bucket-policy-current-lab.json`. It denies S3 requests when `aws:SecureTransport` is `false`, enforcing HTTPS/TLS for requests covered by the policy. S3 Block Public Access was observed as enabled in the console.

## Not deployed

The policy does not restrict access among `landing/`, `raw/`, `trusted/`, and `curated/`. Cross-zone isolation remains a documented design requirement, not an implemented control. All three inspected Glue ETL jobs and the e-commerce ingestion Lambda use the shared `LabRole`; do not add broad prefix denies without first separating and testing workload identities and required paths.
