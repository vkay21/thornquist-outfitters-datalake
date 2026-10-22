# Governance Verification Notes — 22 October 2026

Evidence was reviewed in the AWS console for account `672869298071`, region `us-east-1`. This file summarizes screenshots reviewed during the governance work; it does not replace retaining the original screenshots in the project evidence folder.

1. S3 bucket policy page showed the saved `DenyInsecureTransport` statement for bucket `thornquist-outfitters-datalake-672869298071`.
2. AWS Glue job details showed `LabRole` for `thornquist-pos-raw-to-trusted`.
3. AWS Glue job details showed `LabRole` for `thornquist-ecommerce-raw-to-trusted`.
4. AWS Glue job details showed `LabRole` for `thornquist-customer-raw-to-trusted`.
5. Lambda function `thornquist-ecommerce-ingestion` → Configuration → Permissions showed execution role `LabRole`. Its resource summary displayed `AccessDenied` for `iam:GetPolicy`, with an explicit deny in the Learner Lab identity-based policy.
6. Lake Formation Data permissions displayed `AccessDenied` for `lakeformation:ListPermissions`; the curated database details page displayed `AccessDenied` for `ram:ListPrincipals`. No grant was submitted.

## Interpretation

The errors document specific denied inspection operations; they do not establish that all Lake Formation grants or all Lambda operations are blocked. The e-commerce function's execution health should be judged from its invocation/error metrics and end-to-end tests, not from the inability to inspect a policy.

## Current status

- Deployed: S3 HTTPS-only policy.
- Observed: S3 Block Public Access enabled.
- Not deployed: cross-zone S3 access restrictions and Lake Formation analyst grants.
- Proposed only: curated-only analyst permission design.
