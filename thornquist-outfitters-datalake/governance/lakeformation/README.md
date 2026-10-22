# Lake Formation Permission Design

**Status: proposed design only — not deployed or verified.**

## Intended analyst access

The proposed principal name `thornquist-analyst` is a placeholder for a dedicated analyst identity; it was not found in the Learner Lab role list. The intended access is:

- Database `thornquist_curated`: `DESCRIBE`
- Table `fact_sales`: `SELECT`, `DESCRIBE`
- Table `dim_customer`: `SELECT`, `DESCRIBE`
- Table `agg_daily_sales`: `SELECT`, `DESCRIBE`
- No analyst access to the upstream `landing/`, `raw/`, or `trusted/` zones.

## Evidence observed on 22 October 2026

- The Lake Formation Data permissions page returned `AccessDenied` for `lakeformation:ListPermissions` on the account catalog.
- The curated database details page also showed `AccessDenied` for `ram:ListPrincipals` when inspecting resource shares.
- The Lambda function `thornquist-ecommerce-ingestion` showed `AccessDenied` for `iam:GetPolicy`, with an explicit deny in the Learner Lab identity-based policy. This is an IAM policy-inspection limitation; it does not by itself prove that the Lambda function is failing.
- The three Glue jobs `thornquist-pos-raw-to-trusted`, `thornquist-ecommerce-raw-to-trusted`, and `thornquist-customer-raw-to-trusted` all use `LabRole`. The Lambda function also uses `LabRole`.
- No Lake Formation grant was submitted. The permissions above remain proposed and must not be represented as active.

## S3 policy status and cross-zone isolation

The bucket policy currently deployed on `thornquist-outfitters-datalake-672869298071` denies S3 requests using insecure transport (`aws:SecureTransport = false`). S3 Block Public Access was observed as enabled. The policy does **not** restrict access between storage zones.

Because the Glue jobs and the Lambda function share `LabRole`, a blanket deny based on that role or on prefixes could block legitimate ingestion and transformation paths. Cross-zone isolation is therefore **not deployed**. A safer production design would separate workload and analyst identities, scope each identity to the minimum required prefixes, align those policies with Lake Formation and registered data-location permissions, then test both permitted and denied paths.

## Suggested validation in an unrestricted account

1. Create or identify a dedicated analyst identity and separate workload roles.
2. Grant `DESCRIBE` on `thornquist_curated`.
3. Grant `SELECT` and `DESCRIBE` on `fact_sales`, `dim_customer`, and `agg_daily_sales`.
4. Ensure analyst IAM/S3 permissions do not provide alternate access to landing, raw, or trusted objects.
5. Test successful curated queries and denied upstream access using the analyst identity.
6. Record the active grants and test outcomes before claiming enforcement.

## Scope note

This document records observed console evidence and a proposed permission model. It is not an AWS API payload and does not create or grant permissions. Lake Formation permissions must be considered together with IAM, S3 bucket/object permissions, and the data-lake location role.
