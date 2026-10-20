# Infrastructure and S3 Data Lake Zones

## Overview

This document describes the Amazon S3 storage zones and infrastructure used by the Thornquist Outfitters Retail Data Lake project.

The data lake stores POS sales, e-commerce orders, and customer records in Amazon S3. AWS Glue supports data discovery and processing, while Amazon Athena supports SQL-based analysis.

## AWS Environment

- **AWS Region:** `us-east-1`
- **S3 Bucket:** `thornquist-outfitters-datalake-672869298071`
- **Glue Database:** `thornquist_retail`

The project reuses the existing AWS resources wherever possible to reduce unnecessary deployments and costs.

## S3 Data Lake Zones

The project uses the following S3 prefixes as logical data zones:

| Zone | Purpose |
|---|---|
| `landing/` | Receives incoming source files from the ingestion mechanisms. |
| `raw/` | Stores ingested source data for downstream processing. |
| `trusted/` | Stores transformed and standardized data. |
| `curated/` | Intended for datasets prepared for business analysis. |
| `quarantine/` | Intended to hold records rejected or flagged by data-quality checks. |

These zones are prefixes within the same S3 bucket, not separate S3 buckets.

## Current Infrastructure

The following AWS components have been configured or used during project development:

- **Amazon S3:** Stores source files and processed datasets.
- **AWS Lambda:** Handles e-commerce JSON ingestion triggered by matching S3 events.
- **AWS Glue crawlers:** Discover source data structures.
- **AWS Glue Data Catalog:** Stores table definitions and schemas.
- **AWS Glue ETL jobs:** Process POS data and support customer ingestion.
- **Amazon Athena:** Queries cataloged datasets stored in S3.

Additional data-quality, curated-processing, governance, and monitoring components must be verified against the team's final integrated deployment.

## Infrastructure as Code (IaC)

Infrastructure as Code (IaC) means defining infrastructure using configuration files instead of relying entirely on manual console configuration.

The project repository contains infrastructure and deployment-related directories. Their scripts and configurations must be reviewed to determine which resources are created automatically and which existing resources were configured manually.

This documentation does not claim that the existing S3 bucket or all AWS resources were created using Terraform.

## S3 Security and Cost Considerations

The existing bucket configuration was reviewed during project development. The bucket has public access blocking enabled, ACLs disabled, and default server-side encryption using Amazon S3 managed keys (SSE-S3).

Operational precautions:

- Reuse existing resources when appropriate.
- Avoid running Glue jobs unnecessarily.
- Keep the customer daily ingestion schedule deactivated until the team agrees to the joint test.
- Review deployment and teardown scripts before executing them.
- Verify resource permissions and costs before creating additional infrastructure.
- Do not store access tokens, passwords, or other secrets in source code or GitHub.

## Planned Integration

The team has proposed organizing source data under the following prefixes:

- `raw/pos/`
- `raw/ecommerce/`
- `raw/customer/`

The current source files include objects directly under `raw/`. The team must agree on the final file locations and update the corresponding Glue crawler targets before running the integrated pipeline.

The curated and quarantine zones should be considered complete only after their processing and data-quality behavior have been tested.

## Verification

Before the final demonstration, verify:

1. The S3 source files are available at the agreed locations.
2. Glue crawlers point to the intended folders and update the Data Catalog correctly.
3. The POS transformation produces the expected Trusted output.
4. The integrated pipeline handles valid and invalid records as intended.
5. Access controls and monitoring artifacts match the final implementation.
6. Unneeded resources are not left running after testing.
