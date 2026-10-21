# Thornquist Outfitters — Schema Conflict Reconciliation

## Purpose

The POS, e-commerce, and legacy customer sources use different formats,
field names, identifiers, and levels of detail. This document explains
the conflicts, their business impact, and how the pipeline reconciles
or handles them.

## Conflict 1: Dates and timestamps

**Sources**
- POS: `sale_date` is supplied as a date string. Some records use
  `YYYY-MM-DD`, while others use `DD/MM/YYYY`.
- E-commerce: `order_timestamp` is an ISO-8601 UTC timestamp.
- Customer extract: `signup_date` may also require date normalization.

**Business impact**

Inconsistent date formats can cause parsing failures, incorrect daily
sales totals, and inconsistent comparisons between online and store
sales. UTC timestamps can also fall on a different calendar day from
the Toronto business day.

**Pipeline handling**

- POS processing parses both `yyyy-MM-dd` and `dd/MM/yyyy`, then writes
  a standardized `sale_date`.
- E-commerce processing parses the UTC order timestamp and derives
  `sale_date` using the configured business timezone.
- Customer processing trims input values and applies date validation.

**Evidence**

- `glue_jobs/raw_to_trusted_pos.py`
- `glue_jobs/raw_to_trusted_ecommerce.py`
- `glue_jobs/raw_to_trusted_customer.py`
- `evidence/local_run/dq_report_pos.json`

The POS report records 33 date-format remediations.

## Conflict 2: Customer identifier names and semantics

**Sources**
- POS uses `cust_num`.
- E-commerce uses `cust_ref`.
- The customer master uses the legacy `cust_num` identifier.
- POS uses `0000000` as a walk-in placeholder rather than a real
  customer identifier.

**Business impact**

Joining sources without reconciling the identifiers can produce
unmatched customers, incorrect customer-segment reporting, or false
customer records for walk-in purchases.

**Pipeline handling**

- E-commerce maps `cust_ref` to the common `cust_num` field.
- POS converts the `0000000` walk-in placeholder to null and retains
  walk-in status separately.
- Customer references are checked against the customer master.
  Orphaned references are flagged rather than automatically discarding
  otherwise valid sales.

**Evidence**

- `glue_jobs/raw_to_trusted_ecommerce.py`
- `glue_jobs/raw_to_trusted_pos.py`
- `glue_jobs/trusted_to_curated.py`
- `evidence/local_run/dq_report_pos.json`
- `evidence/local_run/dq_report_ecommerce.json`

The POS report records 185 placeholder-to-null remediations.
The e-commerce report records 35 customer-reference failures flagged
by its referential-integrity rule.

## Conflict 3: Product category representation

**Sources**
- POS supplies a product `category` field.
- E-commerce supplies product SKUs, with category information encoded
  in the SKU prefix.

**Business impact**

Grouping sales by raw source values could create inconsistent
categories and make comparisons between store and online sales
unreliable.

**Pipeline handling**

- E-commerce maps recognized SKU prefixes to the shared category
  taxonomy.
- POS category values are checked against the configured valid
  category domain.
- The curated sales model uses a common `category` field.

**Evidence**

- `glue_jobs/raw_to_trusted_ecommerce.py`
- `glue_jobs/raw_to_trusted_pos.py`
- `glue_jobs/trusted_to_curated.py`
- `evidence/local_run/dq_report_pos.json`
- `evidence/local_run/dq_report_ecommerce.json`

The reports show that category-domain and SKU-prefix validation rules
are implemented. The code and rule definitions are evidence of the
reconciliation approach; they do not by themselves prove that every
possible category mapping has been tested.

## Conflict 4: Flat CSV records versus nested JSON order items

**Sources**
- POS arrives as CSV with transaction and product information in
  tabular rows.
- E-commerce arrives as JSON orders containing an `items` array.
  One order can contain multiple product lines.

**Business impact**

The two sources have different structures and levels of detail.
Counting each JSON order as one sales line would lose product-level
detail and could make quantity, revenue, and category analysis
inconsistent with POS.

**Pipeline handling**

- E-commerce processing expands the nested `items` array into
  individual product-line records.
- Order-level checks validate required fields, uniqueness, quantities,
  prices, and the consistency of `order_total`.
- The curated model conforms both sources to a common sales-line
  structure, with fields such as `order_id`, `line_no`, `quantity`,
  `unit_price`, `line_revenue`, `channel`, and `sale_date`.
- The curated fact table is stored as partitioned Parquet by `channel`
  and `sale_date`.

**Evidence**

- `glue_jobs/raw_to_trusted_ecommerce.py`
- `glue_jobs/trusted_to_curated.py`
- `evidence/local_run/dq_report_ecommerce.json`

The e-commerce report records 265 rows checked, 260 promoted,
and 5 quarantined for duplicate order identifiers. This demonstrates
a recorded data-quality outcome for the local report batch.

## Promotion and quarantine policy

The pipeline uses rule-specific actions:

- **Reject/quarantine:** invalid mandatory fields, duplicate identifiers,
  invalid values, or failed checks configured with the REJECT action.
- **Flag and promote:** issues such as customer-reference mismatches
  where the sales record may remain useful for revenue reporting.
- **Remediate and promote:** deterministic normalization, such as date
  standardization, whitespace trimming, and walk-in placeholder
  conversion, followed by validation.

The batch reports record a 5% maximum rejection threshold. A batch can
be promoted when its rejection percentage is within the configured
threshold, while individual invalid records are quarantined.

## Evidence and limitations

The local reports are useful evidence of implemented rules and
recorded outcomes. AWS Glue run reports and S3 quarantine objects
should also be retained as evidence of the deployed pipeline.

This document describes the reconciliation logic visible in the
project scripts and reports. It does not claim that every possible
source-data variation has been tested.
