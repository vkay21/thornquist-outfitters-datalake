# Data Ingestion

## Overview

This directory documents the three data ingestion mechanisms used in the Thornquist Outfitters Retail Data Lake project. The mechanisms bring point-of-sale (POS), e-commerce, and customer data into Amazon S3 for downstream processing.

**AWS Region:** `us-east-1`

**S3 Bucket:** `thornquist-outfitters-datalake-672869298071`

## 1. POS Sales CSV — Manual or Scripted Upload

**Source file:** `pos_sales_2026-08-24_to_2026-08-30.csv`

**Mechanism:** Manual or scripted upload to Amazon S3.

The POS sales dataset contains retail transaction information, including transaction IDs, store details, sale dates, product information, quantities, prices, payment methods, and customer IDs.

The file is uploaded to the S3 Landing zone and ingested into the Raw zone. The POS Glue ETL job processes the sales data and writes transformed output in Parquet format to `trusted/pos/`.

The existing POS transformation standardizes supported date formats, trims product names, and removes exact duplicate rows.

**Status:** Upload and POS transformation have been tested.

## 2. E-commerce Orders JSON — S3 Event and Lambda

**Source file:** `ecommerce_orders.json`

**Mechanism:** Amazon S3 event notification triggers an AWS Lambda function.

The `thornquist-ecommerce-ingestion` Lambda function is configured to respond to matching JSON object-creation events under the `landing/` prefix. It copies the incoming JSON file into the Raw zone.

The source file contains a top-level JSON array of order objects, including order information, customer references, order timestamps, and nested item details.

The current Lambda function handles file ingestion. It does not flatten the nested order items or perform the complete data-cleaning process. Additional Glue processing is required for those transformations.

**Status:** The Lambda function is deployed, its S3 trigger is configured, and a manual test has succeeded.

## 3. Customer CSV — Glue Ingestion Job

**Source file:** `customer_extract.csv`

**Mechanism:** AWS Glue job with a daily schedule configured for automated ingestion.

The `thornquist-customer-landing-to-raw` Glue job supports moving customer data from the Landing zone into the Raw zone.

The daily schedule is currently deactivated to avoid unintended executions before the team's joint pipeline test.

**Status:** The Glue job exists. Scheduled execution is not currently active and must be verified during the agreed demonstration.

## S3 Data Locations

The project uses the following logical zones:

- `landing/` — incoming source files.
- `raw/` — ingested source data.
- `trusted/` — transformed and standardized data.
- `curated/` — datasets prepared for analytics.
- `quarantine/` — records held for quality review.

The current source files include objects directly under `raw/`. The team has proposed standardizing the source-specific locations to `raw/pos/`, `raw/ecommerce/`, and `raw/customer/`. These paths and the corresponding Glue crawler targets must be aligned before the integrated pipeline is run.

## Verification and Evidence

The following evidence has been collected or reported during development:

- Source files are present in the project S3 bucket.
- The e-commerce Lambda trigger and ingestion function have been tested.
- Glue crawlers and Data Catalog tables have been created for the source datasets.
- The POS Raw-to-Trusted Glue job has completed successfully.
- Athena has been used to inspect the POS output.

Screenshots and supporting evidence should be maintained in the project's `evidence/` directory.

## Operational Notes

- Keep the customer daily schedule deactivated until the team agrees to run the integrated pipeline.
- Coordinate changes to S3 paths and crawler targets with the team.
- Do not run additional Glue jobs or deploy new resources until the joint test is agreed upon.
- Record any changes to ingestion behavior and verify them against the final pipeline configuration.
