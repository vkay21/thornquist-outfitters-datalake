"""
Glue job: tq-raw-to-trusted-pos   (DQ gate for store point-of-sale exports)
Raw daily POS CSVs -> remediation -> DQ gate -> trusted/pos_sales (Parquet, partitioned by sale_date)

NOTE FOR INTEGRATION: Aish's POS raw->trusted job already handles conformance. This
script is written so it can either (a) replace the final write step of that job, or
(b) be called with the same raw path and produce trusted/pos_sales directly. Keep ONE
of them in the Glue workflow, not both.

Arguments
  --raw_path               s3://<bucket>/raw/pos/
  --trusted_customers_path s3://<bucket>/trusted/customers/
  --trusted_path           s3://<bucket>/trusted/pos_sales/
  --quarantine_path        s3://<bucket>/quarantine/pos/
  --report_path            s3://<bucket>/dq_reports/pos/
  --max_reject_pct         optional, default 5
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

from pyspark.sql import functions as F
from pyspark.sql import types as T

import tq_common as C
from tq_dq import FLAG, REJECT, Rule, add_remediation, duplicate_rank, run_gate

args = C.get_args(
    ["raw_path", "trusted_customers_path", "trusted_path", "quarantine_path", "report_path"],
    {"max_reject_pct": "5"},
)
ctx = C.JobContext(args)
spark = ctx.spark

cols = ["transaction_id", "store_id", "store_name", "region", "sale_date", "category",
        "product_name", "quantity", "unit_price", "payment_method", "cust_num"]
# All strings on read: keeps "0000000" intact and lets mixed date formats be detected.
raw = (
    spark.read.option("header", "true")
    .schema(T.StructType([T.StructField(c, T.StringType()) for c in cols]))
    .csv(args["raw_path"])
    .withColumn("_source_file", F.input_file_name())
    .withColumn("_ingest_seq", F.monotonically_increasing_id())
)

# ---- Remediation ----------------------------------------------------------------
df = raw
for c in ["store_name", "region", "category", "product_name", "payment_method", "cust_num", "sale_date"]:
    cleaned = F.trim(F.regexp_replace(F.col(c), " ", " "))
    df = add_remediation(df, F.col(c) != cleaned, f"trimmed_whitespace:{c}")
    df = df.withColumn(c, cleaned)
df = df.withColumn("payment_method", F.upper("payment_method"))

# C1 - dates: ISO from most terminals, DD/MM/YYYY from one mis-configured terminal.
iso = F.to_date(F.col("sale_date"), "yyyy-MM-dd")
dmy = F.when(F.col("sale_date").rlike(r"^\d{2}/\d{2}/\d{4}$"), F.to_date(F.col("sale_date"), "dd/MM/yyyy"))
df = add_remediation(df, iso.isNull() & dmy.isNotNull(), "date_reformatted:sale_date_ddmmyyyy")
df = df.withColumn("sale_date_parsed", F.coalesce(iso, dmy))

# Placeholder customer -> explicit walk-in flag, NULL key (never join on a fake ID).
df = df.withColumn("is_walk_in", F.col("cust_num") == C.WALK_IN_PLACEHOLDER)
df = add_remediation(df, F.col("is_walk_in"), "placeholder_to_null:cust_num_0000000")
df = df.withColumn("cust_num", F.when(F.col("is_walk_in"), F.lit(None)).otherwise(F.col("cust_num")))

df = df.withColumn("quantity_i", F.col("quantity").cast("int"))
df = df.withColumn("unit_price_d", F.col("unit_price").cast("decimal(10,2)"))
df = df.withColumn("_dup_rank", duplicate_rank(["transaction_id"]))

customers = spark.read.parquet(args["trusted_customers_path"]).select(F.col("cust_num").alias("_ref_cust")).distinct()
df = df.join(F.broadcast(customers), df.cust_num == customers._ref_cust, "left")

rules = [
    Rule("POS-01", "mandatory fields present", "completeness", REJECT,
         F.col("transaction_id").isNull() | F.col("store_id").isNull() | F.col("sale_date").isNull()
         | F.col("product_name").isNull() | (F.col("product_name") == "") | F.col("quantity").isNull()
         | F.col("unit_price").isNull(),
         "transaction_id, store_id, sale_date, product_name, quantity, unit_price must be non-empty."),
    Rule("POS-02", "transaction_id unique", "uniqueness", REJECT, F.col("_dup_rank") > 1,
         "Terminal batch re-sends: first copy promoted, repeats quarantined."),
    Rule("POS-03", "sale_date parseable and plausible", "validity", REJECT,
         F.col("sale_date_parsed").isNull()
         | (F.col("sale_date_parsed") > F.date_add(F.current_date(), 1))
         | (F.col("sale_date_parsed") < F.lit("2020-01-01").cast("date")),
         "After remediating DD/MM/YYYY, anything still unparseable or out of range is rejected."),
    Rule("POS-04", "quantity integer between 1 and 50", "range", REJECT,
         F.col("quantity_i").isNull() | (F.col("quantity_i") < 1) | (F.col("quantity_i") > 50),
         "Returns are a separate feed; zero/negative or bulk quantities are suspicious."),
    Rule("POS-05", "unit_price between 0.01 and 5000", "range", REJECT,
         F.col("unit_price_d").isNull() | (F.col("unit_price_d") <= 0) | (F.col("unit_price_d") > 5000),
         "Catches placeholder 0.00 prices and decimal-shift errors."),
    Rule("POS-06", "region/category/payment in reference domains", "validity", REJECT,
         ~F.col("region").isin(C.VALID_REGIONS) | ~F.col("category").isin(C.VALID_CATEGORIES)
         | ~F.col("payment_method").isin(C.VALID_PAYMENT_METHODS),
         "Curated aggregates group by these columns, so unknown values must not leak in."),
    Rule("POS-07", "cust_num well-formed", "validity", REJECT,
         F.col("cust_num").isNotNull() & ~F.col("cust_num").rlike(r"^\d{6}$"),
         "Non-walk-in customer numbers must be 6 digits."),
    Rule("POS-08", "cust_num exists in customer master", "referential_integrity", FLAG,
         F.col("cust_num").isNotNull() & F.col("_ref_cust").isNull(),
         "Orphaned customer: revenue is real so the sale is promoted, flagged for steward follow-up."),
]

promotable, report = run_gate(
    df, rules, source="pos", batch_id=args["batch_id"], max_reject_pct=float(args["max_reject_pct"]),
    quarantine_path=args["quarantine_path"], report_path=args["report_path"],
    write_parquet=C.write_parquet, write_json_report=C.write_json_report,
)

trusted = promotable.select(
    F.col("transaction_id").cast("bigint").alias("transaction_id"),
    F.col("store_id").cast("int").alias("store_id"),
    "store_name", "region",
    F.col("sale_date_parsed").alias("sale_date"),
    "category", "product_name",
    F.col("quantity_i").alias("quantity"),
    F.col("unit_price_d").alias("unit_price"),
    (F.col("quantity_i") * F.col("unit_price_d")).cast("decimal(12,2)").alias("line_revenue"),
    F.lit(C.CURRENCY).alias("currency"),
    "payment_method", "cust_num", "is_walk_in",
    F.array_contains("dq_flags", "POS-08").alias("is_orphan_customer"),
    "dq_flags", "dq_remediations",
    F.lit(args["batch_id"]).alias("dq_batch_id"),
    "_source_file",
    F.current_timestamp().alias("_loaded_at"),
)
C.write_parquet(trusted, args["trusted_path"], partition_cols=["sale_date"])
C.publish_metrics("pos", {k: report[k] for k in ("rows_checked", "rows_promoted", "rows_quarantined")})
ctx.commit()
