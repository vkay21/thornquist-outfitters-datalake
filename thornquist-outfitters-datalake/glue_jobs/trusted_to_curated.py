"""
Glue job: thornquist-trusted-to-curated
trusted/{pos, ecommerce, customer}
  -> curated/fact_sales       (one conformed sales model, Parquet, partitioned by channel + sale_date)
  -> curated/dim_customer     (Parquet, small, unpartitioned)
  -> curated/agg_daily_sales  (pre-aggregated for the dashboard, Parquet)

Conformed model resolves the cross-channel schema conflicts:
  C1 date formats       -> one DATE `sale_date` (business day, America/Toronto)
  C2 customer keys      -> one STRING `cust_num` (POS cust_num, e-com cust_ref; walk-ins NULL)
  C3 product taxonomy   -> one `category` (POS category name; e-com SKU prefix mapped)
  C4 region semantics   -> one `region` (store location for POS, shipping region for e-com)
  C5 time zone/grain    -> e-com UTC timestamp kept as sale_ts_utc; POS has date only

Arguments
  --pos_path        s3://<bucket>/trusted/pos/        (Aish's job OR thornquist-pos-dq-gate)
  --ecommerce_path  s3://<bucket>/trusted/ecommerce/
  --customers_path  s3://<bucket>/trusted/customer/
  --curated_path    s3://<bucket>/curated/
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

from pyspark.sql import functions as F

import tq_common as C

args = C.get_args(["pos_path", "ecommerce_path", "customers_path", "curated_path"])
ctx = C.JobContext(args)
spark = ctx.spark
OUT = lambda p: C.join_path(args["curated_path"], p)  # noqa: E731

pos = spark.read.option("recursiveFileLookup", "false").parquet(args["pos_path"])
eco = spark.read.parquet(args["ecommerce_path"])
cust = spark.read.parquet(args["customers_path"])


def conform_pos(df, customers):
    """Accept either POS trusted schema.

    * thornquist-pos-dq-gate output already carries is_walk_in / is_orphan_customer / dq_flags.
    * Aish's thornquist-pos-raw-to-trusted output keeps the source columns: sale_date as a
      yyyy-MM-dd STRING, the 0000000 walk-in placeholder, and cust_num possibly typed as a
      number by the crawler. Conform it here so both paths give identical curated rows.
    """
    if "is_walk_in" in df.columns:
        return df
    cust_s = F.trim(F.col("cust_num").cast("string"))
    walk = cust_s.isNull() | cust_s.isin(C.WALK_IN_PLACEHOLDER, "0") | (cust_s == "")
    ref = customers.select(F.col("cust_num").alias("_ref_cust")).distinct()
    out = (
        df.withColumn("is_walk_in", walk)
        .withColumn("cust_num", F.when(walk, F.lit(None)).otherwise(F.lpad(cust_s, 6, "0")))
        .withColumn("sale_date", F.coalesce(F.to_date(F.col("sale_date").cast("string"), "yyyy-MM-dd"),
                                            F.to_date(F.col("sale_date").cast("string"), "dd/MM/yyyy")))
        # Spark's trim() does not remove U+00A0, so normalise it explicitly.
        .withColumn("product_name", F.trim(F.regexp_replace("product_name", " ", " ")))
        .withColumn("transaction_id", F.col("transaction_id").cast("bigint"))
        .withColumn("store_id", F.col("store_id").cast("int"))
        .withColumn("quantity", F.col("quantity").cast("int"))
        .withColumn("unit_price", F.col("unit_price").cast("decimal(10,2)"))
        .withColumn("line_revenue", (F.col("quantity") * F.col("unit_price")).cast("decimal(12,2)"))
        .withColumn("currency", F.lit(C.CURRENCY))
        .withColumn("payment_method", F.upper(F.trim("payment_method")))
        .join(F.broadcast(ref), F.col("cust_num") == F.col("_ref_cust"), "left")
        .withColumn("is_orphan_customer", F.col("cust_num").isNotNull() & F.col("_ref_cust").isNull())
        .withColumn("dq_flags", F.when(F.col("is_orphan_customer"), F.array(F.lit("POS-08")))
                    .otherwise(F.array().cast("array<string>")))
    )
    # Exact-duplicate removal (SELECT DISTINCT) does not catch a re-sent transaction_id
    # whose other fields differ; keep one row per transaction_id defensively.
    return out.dropDuplicates(["transaction_id"])


pos = conform_pos(pos, cust)

pos_c = pos.select(
    F.concat(F.lit("POS-"), F.col("transaction_id").cast("string"), F.lit("-1")).alias("sales_line_id"),
    F.lit("store").alias("channel"),
    F.col("transaction_id").alias("order_id"),
    F.lit(1).alias("line_no"),
    F.col("sale_date"),
    F.lit(None).cast("timestamp").alias("sale_ts_utc"),
    "store_id", "store_name", "region",
    "category", "product_name",
    F.lit(None).cast("string").alias("sku"),
    "quantity", "unit_price", "line_revenue", "currency", "payment_method",
    "cust_num", "is_walk_in", "is_orphan_customer",
    (F.size("dq_flags") > 0).alias("dq_flagged"),
)
eco_c = eco.select(
    F.concat(F.lit("WEB-"), F.col("order_id").cast("string"), F.lit("-"), F.col("line_no").cast("string")).alias("sales_line_id"),
    F.col("channel"),
    "order_id", "line_no", "sale_date",
    F.col("order_ts_utc").alias("sale_ts_utc"),
    F.lit(None).cast("int").alias("store_id"),
    F.lit("E-commerce").alias("store_name"),
    F.col("shipping_region").alias("region"),
    "category", "product_name", "sku",
    "quantity", "unit_price", "line_revenue", "currency",
    F.lit(None).cast("string").alias("payment_method"),
    "cust_num",
    F.lit(False).alias("is_walk_in"),
    "is_orphan_customer",
    (F.size("dq_flags") > 0).alias("dq_flagged"),
)
sales = pos_c.unionByName(eco_c)

# Denormalise the two customer attributes analysts filter on most, so the common
# segment queries need no join (curated = query-shaped, not normalised).
cust_attrs = cust.select("cust_num", "loyalty_tier", F.col("home_region").alias("customer_home_region"))
fact = (
    sales.join(F.broadcast(cust_attrs), "cust_num", "left")
    .withColumn(
        "customer_segment",
        F.when(F.col("is_walk_in"), "Walk-in")
        .when(F.col("loyalty_tier").isNull(), "Unmatched")
        .otherwise(F.col("loyalty_tier")),
    )
    .withColumn("sale_week", F.date_trunc("week", F.col("sale_date")).cast("date"))
    .withColumn("_loaded_at", F.current_timestamp())
)
fact_cols = ["sales_line_id", "order_id", "line_no", "sale_ts_utc", "sale_week", "store_id", "store_name", "region",
             "category", "product_name", "sku", "quantity", "unit_price", "line_revenue", "currency", "payment_method",
             "cust_num", "is_walk_in", "is_orphan_customer", "loyalty_tier", "customer_home_region", "customer_segment",
             "dq_flagged", "_loaded_at", "channel", "sale_date"]
fact = fact.select(*fact_cols)
# One file per partition: avoids the small-files problem Athena pays for per object.
C.write_parquet(fact.repartition("channel", "sale_date"), OUT("fact_sales"), partition_cols=["channel", "sale_date"])

dim = cust.select(
    "cust_num", "first_name", "last_name", "email",  # PII: hidden from analysts by Lake Formation column filter
    "signup_date", F.year("signup_date").alias("signup_year"), "loyalty_tier", "home_region",
    F.current_timestamp().alias("_loaded_at"),
)
C.write_parquet(dim.coalesce(1), OUT("dim_customer"))

agg = (
    fact.groupBy("sale_date", "channel", "region", "category")
    .agg(
        F.countDistinct("order_id").alias("orders"),
        F.count(F.lit(1)).alias("sales_lines"),
        F.sum("quantity").alias("units"),
        F.sum("line_revenue").cast("decimal(14,2)").alias("revenue"),
    )
)
C.write_parquet(agg.coalesce(1), OUT("agg_daily_sales"))

n = fact.count()
print(f"[curated] fact_sales rows: {n}")
C.publish_metrics("curated", {"fact_sales_rows": n}, namespace="Thornquist/Pipeline")
ctx.commit()
