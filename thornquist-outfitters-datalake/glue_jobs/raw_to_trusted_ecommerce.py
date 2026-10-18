"""
Glue job: tq-raw-to-trusted-ecommerce
Raw storefront order JSON (nested items[]) -> order-level DQ gate -> explode to lines
-> trusted/ecommerce_order_lines (Parquet, partitioned by sale_date)

Schema evolution (stretch goal): unknown top-level attributes that the storefront adds
later (e.g. "promo_code") do NOT break the job - they are preserved as a JSON string in
`extra_attributes` and reported in the DQ report, so the catalogued schema stays stable.

Arguments
  --raw_path               s3://<bucket>/raw/ecommerce/
  --trusted_customers_path s3://<bucket>/trusted/customers/
  --trusted_path           s3://<bucket>/trusted/ecommerce_order_lines/
  --quarantine_path        s3://<bucket>/quarantine/ecommerce/
  --report_path            s3://<bucket>/dq_reports/ecommerce/
  --json_format            optional: "array" (default, one JSON array per file) or "lines" (JSONL)
  --max_reject_pct         optional, default 5
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

from pyspark.sql import functions as F

import tq_common as C
from tq_dq import FLAG, REJECT, Rule, add_remediation, duplicate_rank, run_gate

args = C.get_args(
    ["raw_path", "trusted_customers_path", "trusted_path", "quarantine_path", "report_path"],
    {"max_reject_pct": "5", "json_format": "array"},
)
ctx = C.JobContext(args)
spark = ctx.spark

KNOWN_FIELDS = ["order_id", "order_timestamp", "cust_ref", "channel", "shipping_region", "items", "order_total"]

reader = spark.read.option("multiLine", "true" if args["json_format"] == "array" else "false")
raw = reader.json(args["raw_path"])
PARTITION_COLUMNS = {"ingest_date", "dt", "year", "month", "day", "hour"}  # S3 folder partitions, not payload
extra_fields = sorted(c for c in raw.columns
                      if c not in KNOWN_FIELDS and c not in PARTITION_COLUMNS and not c.startswith("_corrupt"))
for c in KNOWN_FIELDS:  # tolerate a field disappearing too
    if c not in raw.columns:
        raw = raw.withColumn(c, F.lit(None))
raw = (
    raw.withColumn("extra_attributes",
                   F.to_json(F.struct(*[F.col(c) for c in extra_fields])) if extra_fields else F.lit(None).cast("string"))
    .withColumn("_source_file", F.input_file_name())
    .withColumn("_ingest_seq", F.monotonically_increasing_id())
)
if extra_fields:
    print(f"[schema] new top-level attributes detected and preserved in extra_attributes: {extra_fields}")

# ---- Remediation / conformance (order level) -------------------------------------
df = raw.withColumn("cust_num", F.col("cust_ref").cast("string"))  # C2: cust_ref -> cust_num
for c in ["shipping_region", "channel"]:
    cleaned = F.trim(F.regexp_replace(F.col(c).cast("string"), " ", " "))
    df = add_remediation(df, F.col(c) != cleaned, f"trimmed_whitespace:{c}")
    df = df.withColumn(c, cleaned)
df = df.withColumn("channel", F.lower("channel"))
df = df.withColumn("order_ts_utc", F.to_timestamp("order_timestamp"))  # ISO-8601 'Z' (UTC)
df = df.withColumn("_dup_rank", duplicate_rank(["order_id"]))
df = df.withColumn(
    "_items_total",
    F.aggregate("items", F.lit(0.0).cast("double"), lambda acc, i: acc + i["qty"].cast("double") * i["unit_price"].cast("double")),
)

customers = spark.read.parquet(args["trusted_customers_path"]).select(F.col("cust_num").alias("_ref_cust")).distinct()
df = df.join(F.broadcast(customers), df.cust_num == customers._ref_cust, "left")

valid_prefixes = "|".join(C.SKU_PREFIX_TO_CATEGORY)
rules = [
    Rule("ECO-01", "mandatory fields present, at least one item", "completeness", REJECT,
         F.col("order_id").isNull() | F.col("order_timestamp").isNull() | F.col("cust_ref").isNull()
         | F.col("items").isNull() | (F.size("items") < 1),
         "order_id, order_timestamp, cust_ref and a non-empty items array are required."),
    Rule("ECO-02", "order_id unique", "uniqueness", REJECT, F.col("_dup_rank") > 1,
         "Webhook retries deliver the same order twice: first copy promoted, repeats quarantined."),
    Rule("ECO-03", "order_timestamp parseable and plausible", "validity", REJECT,
         F.col("order_ts_utc").isNull() | (F.col("order_ts_utc") > F.current_timestamp())
         | (F.col("order_ts_utc") < F.lit("2020-01-01").cast("timestamp")),
         "ISO-8601 UTC expected."),
    Rule("ECO-04", "every line qty 1-50 and unit_price 0.01-5000", "range", REJECT,
         F.exists("items", lambda i: i["qty"].isNull() | (i["qty"] < 1) | (i["qty"] > 50)
                  | i["unit_price"].isNull() | (i["unit_price"] <= 0) | (i["unit_price"] > 5000)),
         "One bad line quarantines the whole order so order totals stay consistent."),
    Rule("ECO-05", "SKU matches AAA-9999 with a known category prefix", "validity", REJECT,
         F.exists("items", lambda i: i["sku"].isNull() | ~i["sku"].rlike(f"^({valid_prefixes})-[0-9]{{4}}$")),
         "SKU prefix is how e-commerce lines map to the POS category taxonomy (conflict C3)."),
    Rule("ECO-06", "order_total equals sum(qty x unit_price)", "consistency", REJECT,
         F.col("order_total").isNull() | (F.abs(F.col("order_total") - F.col("_items_total")) > 0.01),
         "Detects truncated item arrays or tampered totals."),
    Rule("ECO-07", "shipping_region and channel in reference domains", "validity", REJECT,
         ~F.col("shipping_region").isin(C.VALID_REGIONS) | ~F.col("channel").isin(C.VALID_ECOM_CHANNELS),
         f"Regions {C.VALID_REGIONS}; channels {C.VALID_ECOM_CHANNELS}."),
    Rule("ECO-08", "cust_ref exists in customer master", "referential_integrity", FLAG,
         F.col("_ref_cust").isNull(),
         "Orphaned customer (deleted or never synced): order promoted with a flag."),
]

promotable, report = run_gate(
    df, rules, source="ecommerce", batch_id=args["batch_id"], max_reject_pct=float(args["max_reject_pct"]),
    quarantine_path=args["quarantine_path"], report_path=args["report_path"],
    write_parquet=C.write_parquet, write_json_report=C.write_json_report,
)

# ---- Explode passing orders into conformed lines ---------------------------------
prefix_map = F.create_map(*[F.lit(x) for kv in C.SKU_PREFIX_TO_CATEGORY.items() for x in kv])
lines = promotable.select("*", F.posexplode("items").alias("_pos", "item"))
trusted = lines.select(
    F.col("order_id").cast("bigint").alias("order_id"),
    (F.col("_pos") + 1).cast("int").alias("line_no"),
    "order_ts_utc",
    F.to_date(F.from_utc_timestamp("order_ts_utc", C.BUSINESS_TIMEZONE)).alias("sale_date"),  # C5
    "channel", "shipping_region", "cust_num",
    F.col("item.sku").alias("sku"),
    prefix_map[F.substring(F.col("item.sku"), 1, 3)].alias("category"),  # C3
    F.trim(F.regexp_replace(F.col("item.product_name"), " ", " ")).alias("product_name"),
    F.col("item.qty").cast("int").alias("quantity"),
    F.col("item.unit_price").cast("decimal(10,2)").alias("unit_price"),
    (F.col("item.qty") * F.col("item.unit_price").cast("decimal(10,2)")).cast("decimal(12,2)").alias("line_revenue"),
    F.col("order_total").cast("decimal(12,2)").alias("order_total"),
    F.lit(C.CURRENCY).alias("currency"),
    F.array_contains("dq_flags", "ECO-08").alias("is_orphan_customer"),
    "extra_attributes", "dq_flags", "dq_remediations",
    F.lit(args["batch_id"]).alias("dq_batch_id"),
    "_source_file",
    F.current_timestamp().alias("_loaded_at"),
)
C.write_parquet(trusted, args["trusted_path"], partition_cols=["sale_date"])
report_metrics = {k: report[k] for k in ("rows_checked", "rows_promoted", "rows_quarantined")}
report_metrics["new_schema_attributes"] = len(extra_fields)
C.publish_metrics("ecommerce", report_metrics)
ctx.commit()
