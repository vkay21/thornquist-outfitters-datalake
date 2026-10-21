# Athena CSV vs Parquet Benchmark

## Test setup

- Workgroup: `thornquist-wg`
- Database: `thornquist_curated`
- Engine: Athena engine 3
- Query: revenue by category for online sales on `2026-08-27`
- Source table: `thornquist_curated.fact_sales`
- The same filters and aggregation were used for all three layouts.

## Results

| Layout | Data scanned | Runtime |
|---|---:|---:|
| CSV, unpartitioned (`bench_fact_csv`) | 40.65 KB | 474 ms |
| Parquet with Snappy, unpartitioned (`bench_fact_parquet_flat`) | 0.51 KB | 554 ms |
| Parquet, partitioned by channel and sale_date (`fact_sales`) | 0.58 KB | 715 ms |

## Interpretation

For this query and sample dataset, unpartitioned Parquet scanned approximately 98.7% fewer bytes than CSV. This demonstrates the benefit of columnar storage for a query that reads selected columns.

The partitioned production table scanned 0.58 KB, slightly more than the unpartitioned Parquet copy at 0.51 KB. At this small scale, the measurements do not demonstrate a scan-size improvement from partitioning. Partitioning can still help when queries filter on partition keys and datasets are larger.

These results are specific to this sample, query, and Athena execution. They should not be treated as a universal performance guarantee.

## Cleanup status

The two temporary benchmark tables were created for this test. Their Glue Catalog entries and S3 data locations must be removed after verifying the locations. The production `fact_sales` table and its data must be retained.
