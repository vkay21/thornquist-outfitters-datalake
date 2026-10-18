-- STRETCH GOAL: CSV vs Parquet, unpartitioned vs partitioned - Athena bytes scanned.
-- Run each block in the thornquist-wg workgroup, then read "Data scanned" from the query
-- history (or: aws athena get-query-execution --query-execution-id <id>
--          --query 'QueryExecution.Statistics.DataScannedInBytes').
-- Record results in docs/benchmark_results.md. Drop the copies afterwards (cost hygiene).

-- 1) Build comparison copies of the same data with CTAS
CREATE TABLE thornquist_curated.bench_fact_csv
WITH (format = 'TEXTFILE', field_delimiter = ',', external_location = 's3://${BUCKET}/curated/_bench/csv/')
AS SELECT * FROM thornquist_curated.fact_sales;

CREATE TABLE thornquist_curated.bench_fact_parquet_flat
WITH (format = 'PARQUET', external_location = 's3://${BUCKET}/curated/_bench/parquet_flat/')
AS SELECT * FROM thornquist_curated.fact_sales;

-- 2) The SAME business query against each layout (one day, one channel, two columns)
-- A. CSV, unpartitioned  -> full scan of every column of every row
SELECT category, SUM(line_revenue) FROM thornquist_curated.bench_fact_csv
WHERE channel = 'online' AND sale_date = '2026-08-27' GROUP BY category;

-- B. Parquet, unpartitioned -> columnar: reads only category/line_revenue/channel/sale_date
SELECT category, SUM(line_revenue) FROM thornquist_curated.bench_fact_parquet_flat
WHERE channel = 'online' AND sale_date = '2026-08-27' GROUP BY category;

-- C. Parquet, partitioned by channel + sale_date (production table) -> 1 of ~16 partitions
SELECT category, SUM(line_revenue) FROM thornquist_curated.fact_sales
WHERE channel = 'online' AND sale_date = '2026-08-27' GROUP BY category;

-- 3) Clean up
DROP TABLE thornquist_curated.bench_fact_csv;
DROP TABLE thornquist_curated.bench_fact_parquet_flat;
-- then: aws s3 rm s3://${BUCKET}/curated/_bench/ --recursive
