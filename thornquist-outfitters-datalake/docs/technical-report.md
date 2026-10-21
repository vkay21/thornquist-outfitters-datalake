# Thornquist Outfitters: Building a Governed Data Lake

**Course:** CCGC 5506 — Emerging Technologies  
**Project:** Mid-Term Project 1  
**Platform:** AWS Academy Learner Lab  
**Region:** us-east-1

## 1. Executive Summary

Thornquist Outfitters is a fictional outdoor retailer that receives business data from physical point-of-sale (POS) systems, an e-commerce storefront, and a legacy customer system. These sources use different structures and identifiers, making it difficult to combine them reliably for reporting. This project implements a zoned, serverless data lake on Amazon Web Services (AWS) to consolidate the data, apply data-quality controls, and provide a consistent analytics layer.

The solution uses Amazon S3 for storage, AWS Glue for ingestion and transformation, AWS Glue Data Catalog for metadata, Amazon Athena for SQL analysis, and Lake Formation and IAM policy artifacts for governance. Data is organized into landing, raw, trusted, and curated zones, with separate quarantine and data-quality report locations. The curated layer contains a sales fact table, a customer dimension, and daily sales aggregates.

The sample data produced a curated fact table containing 1,687 sales lines with approximately $337,945.57 in revenue. Data-quality processing also identified duplicate transactions, placeholder customer identifiers, inconsistent dates, and unmatched customer references. The project demonstrates how data validation and standardization can improve analytical consistency while preserving rejected records for investigation.

## 2. Business Problem and Objectives

The retailer's source systems represent sales and customer information differently. POS data arrives as CSV, e-commerce orders arrive as nested JSON, and customer information is supplied as a separate CSV extract. Differences in date formats, customer identifiers, category values, and record structure make direct analysis unreliable.

The main objective is to create a repeatable pipeline that transforms these source files into a governed analytical dataset. The solution must preserve raw source data, standardize records before promotion, identify invalid data, and make trusted results available for business questions.

The project objectives are to implement four storage zones, demonstrate at least three ingestion mechanisms, document at least four schema conflicts, apply automated data-quality rules, build a partitioned Parquet-based curated layer, provide at least five Athena queries, and document governance controls and implementation limitations.

## 3. Architecture and Data Flow

The architecture is documented in `docs/architecture.mmd`. Amazon S3 provides the storage foundation, while Glue jobs process records through the zones. The landing zone receives incoming files. The raw zone retains source data for traceability and replay. The trusted zone contains standardized Parquet data that has passed the applicable promotion rules. The curated zone contains conformed analytical tables.

Separate quarantine and data-quality report prefixes retain rejected records and processing results.

The ingestion mechanisms are a scripted upload for POS CSV files, an S3 event notification configured to invoke the e-commerce Lambda function for new JSON files under `landing/`, and a scheduled Glue trigger for the customer extract. The Lambda resource policy permits invocation by S3 from the project bucket, and the bucket notification configuration contains the `landing/` prefix and `.json` suffix filters. The customer daily-ingestion trigger is activated and configured for 00:00 UTC.

Three Glue crawlers cover customer, e-commerce, and POS source locations. Their daily schedules are configured for 03:00 UTC and have been verified in the `SCHEDULED` state. Their next scheduled executions have not yet been observed. The curated tables are defined through Athena DDL and use partition projection, reducing the need to crawl the curated output on every update.

A Glue workflow named `thornquist-pipeline` is configured to run customer ingestion first, then POS and e-commerce processing, followed by curated processing after both sales jobs succeed. The two conditional workflow triggers were activated. Their predicates were verified to require the customer transformation to succeed before POS and e-commerce processing, and both sales transformations to succeed before curated processing. A subsequent workflow execution completed successfully, and all four workflow jobs succeeded.

## 4. Ingestion and Storage Zones

The three source datasets are POS sales, e-commerce orders, and the customer extract. The customer extract contains 400 records. The e-commerce input contains 265 orders, and the POS input contains 1,051 rows before data-quality processing.

Amazon S3 separates storage by processing stage. Landing is the entry point for incoming files, and raw retains the original representation. Trusted output uses Parquet, a columnar format suitable for analytical workloads. The curated output includes a sales fact table partitioned by channel and sale date, together with a customer dimension and daily sales aggregates.

The separate quarantine prefix prevents rejected rows from being mixed with accepted records. Data-quality reports record the number of rows checked, promoted, flagged, and quarantined, together with rule outcomes and remediation counts. This separation supports investigation and makes the promotion decision more transparent.

## 5. Schema Conflicts and Reconciliation

Four principal schema conflicts are documented in `docs/schema-conflicts.md`.

First, the sources use different date representations. POS dates are mostly ISO-style dates, but some use day/month/year formatting. E-commerce timestamps use ISO-8601 representations and require conversion to a consistent business date. The POS process standardized 33 dates that used the day/month/year format.

Second, customer identifiers differ between systems. POS uses `cust_num`, while e-commerce provides a customer reference that is normalized to the common customer identifier. POS also uses `0000000` as a walk-in placeholder rather than a genuine customer number. The POS process converted 185 such placeholders to null and represented walk-in status separately. This prevents a placeholder from being treated as an actual customer.

Third, category information is not represented consistently across the two sales sources. The transformation applies category mapping to produce a common analytical representation. This improves cross-channel reporting, although mapping rules should be maintained as product taxonomies change.

Fourth, the source structures differ. POS records are flat CSV rows, while e-commerce orders contain nested item arrays. The e-commerce ETL process flattens order items into sales-line records. This makes it possible to analyze sales at line level rather than treating a multi-item order as one indivisible transaction.

The reconciliation logic also standardizes field types, removes exact duplicate records where appropriate, and aligns the sales sources to a shared fact schema. These steps enable consistent analysis across online and physical-store sales.

## 6. Data Quality and Quarantine

Data quality is enforced before records are promoted into the trusted zone. The rule catalogue covers completeness, uniqueness, date validity, numeric ranges, valid domains, and referential integrity. The processing results are recorded in JSON reports and rejected records are retained under source-specific quarantine prefixes.

The customer batch checked and promoted all 400 records, with no quarantined rows. The customer rules checked required fields, unique customer identifiers, signup dates, loyalty values, email format, and region values.

The POS batch checked 1,051 rows, promoted 1,048, and quarantined three duplicate transaction re-sends. The reported rejection rate was 0.29%, below the configured 5% maximum. The transformation also standardized 33 dates, converted 185 walk-in placeholders to null, and trimmed whitespace from 13 product names. The rules covered required fields, transaction uniqueness, date validity, quantity and price ranges, permitted domains, customer identifier format, and customer-reference integrity.

The e-commerce batch checked 265 orders, promoted 260, and quarantined five duplicate order identifiers. Its rejection rate was 1.89%, also below the 5% threshold. The report identified 35 customer-reference issues under a warning rule, with 34 rows promoted as flagged. This difference between the rule's failed-row count and the promoted flagged count should be reviewed before production use.

The design uses row-level quarantine and a batch circuit-breaker: if the rejection rate exceeds 5%, the batch is intended to fail rather than promote a potentially unreliable batch. A deliberately broken-batch demonstration is documented in the repository's demo runbook; its AWS execution evidence has not yet been demonstrated.

## 7. Curated Model and Analytics

The curated layer contains `fact_sales`, `dim_customer`, and `agg_daily_sales`. The sales fact table brings online and store transactions into one analytical structure. It includes sales identifiers, timestamps, store and product attributes, quantity, unit price, line revenue, customer information, quality flags, channel, and sale date. The customer dimension supports customer-segment analysis, while the aggregate table provides daily sales summaries.

Parquet with Snappy compression was selected for analytical efficiency. The fact table is partitioned by channel and sale date, allowing queries to restrict the data read to relevant partitions. Partition projection is configured for the curated tables to avoid depending on repeated crawler runs for newly created date partitions.

Athena queries provide revenue by channel, daily sales trends, product performance, category analysis, customer-segment behavior, omnichannel customers, demand versus allocation, and data-trust exposure. Eight analytical SQL files are present under `sql/analytics/`.

A verified Athena query returned 639 online sales lines with $123,383.79 in revenue and 1,048 store sales lines with $214,561.78 in revenue. Together, the result was 1,687 lines and $337,945.57. These values describe line-level revenue, not necessarily the number of unique orders. Store sales contributed approximately 63.5% of the total revenue in this sample.

The top-revenue products included Alpine Hiking Shoe at $21,540.35 and Trailrunner Boot at $21,013.61. Segment analysis reported $198,605.76 in revenue for Standard, $62,736.72 for Silver, $35,772.89 for Walk-in, $23,454.98 for Gold, and $17,375.22 for Unmatched. These results illustrate how the curated layer supports cross-channel, product, and customer analysis.

The repository includes exported dashboard figures for key performance indicators, region and channel, category and channel, daily trends, segment average order value, and omnichannel behavior. These figures provide a dashboard fallback when QuickSight is unavailable in the Learner Lab.

The benchmark compared a CSV table, an unpartitioned Parquet table, and the production partitioned Parquet fact table using the same Athena query. The CSV table scanned 40.65 KB in 474 ms; the unpartitioned Parquet table scanned 0.51 KB in 554 ms; and the partitioned production table scanned 0.58 KB in 715 ms. For this query, unpartitioned Parquet scanned approximately 98.7% less data than CSV. Because the dataset is small, the partitioned table did not outperform unpartitioned Parquet in elapsed time or bytes scanned. These results are documented in `docs/benchmark_results.md` and should not be generalized to larger datasets without further testing.

## 8. Governance, Security, and Cost

The governance package contains separate least-privilege IAM policy designs for ingestion, Glue ETL, and analysts, together with production and Learner Lab S3 bucket policies. The project also includes Lake Formation grant definitions, a lifecycle policy, and a RACI matrix.

The Learner Lab uses pre-created roles and restricts the ability to create custom IAM roles. Consequently, the role-specific IAM policies are design artifacts rather than evidence of deployed roles. At the time of verification, no S3 bucket policy was attached and no S3 lifecycle configuration existed. The current `voclabs` role was denied access to Lake Formation resource, permission, and data-lake settings inspection APIs, so live Lake Formation grants and administrator settings could not be verified. These limitations are reported separately from the policy and grant files present in the repository.

Lake Formation is intended to restrict analysts to curated data and to support more specific controls, including column restrictions and a regional row filter. The repository includes the grant script and permission definition; a live permission should be claimed only when verified in the AWS console or CLI.

The project uses an Athena workgroup with a configured result location and a per-query scan limit of 1 GiB. S3 Block Public Access was verified as enabled. Parquet compression and partitioning reduce the amount of data read for analytical queries. The lifecycle policy documents transitions for older data and expiration for temporary locations, but it is not deployed. These controls are designed to reduce storage and query costs, although the small sample and benchmark do not establish production cost savings.

CloudWatch contains POS and e-commerce quarantine-spike alarms. Both alarms were in the `OK` state when checked. The e-commerce Lambda function was `Active` with a successful last update. CloudWatch showed seven recorded invocations across October 15–16, 2026, and zero errors on those two dates. These metrics do not by themselves prove that each invocation was caused by an S3 upload or that every event path has been tested end to end.

## 9. Testing, Results, and Limitations

A Glue workflow execution completed successfully on October 21, 2026. The customer raw-to-trusted, POS raw-to-trusted, e-commerce raw-to-trusted, and trusted-to-curated jobs all succeeded. The curated job wrote partitioned fact data and the customer dimension and daily aggregate outputs to S3. Athena successfully queried the curated fact table and returned the channel revenue figures reported above.

The customer ingestion trigger is activated, all three crawlers have daily schedules in the `SCHEDULED` state, and the S3 bucket notification is configured for the e-commerce Lambda function. These checks verify configuration, but the next scheduled crawler executions have not yet been observed. Similarly, the Lambda resource policy and S3 notification establish the event integration configuration; the recorded invocation metrics do not independently prove that a new upload caused a successful invocation.

The POS and e-commerce quarantine-spike CloudWatch alarms exist and were in the `OK` state when checked. Lambda metrics showed zero errors on the two dates with reported datapoints. The Athena CSV-versus-Parquet benchmark is documented in `docs/benchmark_results.md`, and its temporary benchmark objects and table definitions were cleaned up after testing.

Live Lake Formation grants remain unverifiable with the available Learner Lab permissions. The intentionally rejected bad-batch run has not been demonstrated in AWS. The S3 bucket policy and lifecycle configuration remain undeployed, and the e-commerce local data-quality report has a warning-count discrepancy: 35 customer-reference issues were reported, while 34 rows were promoted as flagged. These items should be addressed or clearly presented as limitations in the final demonstration.

The sample is small and covers only one week of sales data. Additional testing would be needed for larger volumes, evolving source schemas, retries, late-arriving events, and production access patterns. The configured daily schedules should also be monitored to confirm subsequent executions.

## 10. Conclusion

The project establishes a practical foundation for a governed retail data lake using AWS managed services. It demonstrates source-specific ingestion and transformations, explicit schema reconciliation, data-quality reporting, quarantine, a conformed sales model, partitioned Parquet storage, and Athena-based analytics. The sample results show that online and store data can be combined for revenue and customer-segment analysis, while the benchmark illustrates the potential reduction in scanned data from Parquet.

The main remaining focus is to collect final live AWS evidence, demonstrate a rejected bad batch if feasible, and clearly identify governance controls that remain undeployed or unverifiable in the Learner Lab. Separating implemented behavior from intended design makes the deliverable more reliable and provides a clear path from a Learner Lab prototype toward a production-ready architecture.
