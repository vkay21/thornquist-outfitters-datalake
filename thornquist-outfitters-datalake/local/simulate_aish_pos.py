"""
Local stand-in for Aish's Glue job thornquist-pos-raw-to-trusted, built from her description:
  * reads the POS CSV with inferred types (as the crawler/catalog would)
  * normalises sale_date (yyyy-MM-dd and dd/MM/yyyy) to a yyyy-MM-dd STRING
  * trims product_name with Spark's trim()
  * removes exact duplicate rows (SELECT DISTINCT)
  * keeps cust_num as-is (0000000 placeholder retained)
Used only to test that trusted_to_curated.py conforms her output correctly (POS_MODE=aish).
    python local/simulate_aish_pos.py --raw_path <dir> --trusted_path <dir>
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "glue_jobs", "lib"))
from pyspark.sql import functions as F  # noqa: E402

import tq_common as C  # noqa: E402

args = C.get_args(["raw_path", "trusted_path"])
ctx = C.JobContext(args)
df = ctx.spark.read.option("header", "true").option("inferSchema", "true").csv(args["raw_path"])
df = df.drop("ingest_date") if "ingest_date" in df.columns else df
d = F.col("sale_date").cast("string")
df = df.withColumn(
    "sale_date",
    F.when(d.rlike(r"^\d{2}/\d{2}/\d{4}$"), F.date_format(F.to_date(d, "dd/MM/yyyy"), "yyyy-MM-dd"))
    .otherwise(F.date_format(F.to_date(d, "yyyy-MM-dd"), "yyyy-MM-dd")),
)
df = df.withColumn("product_name", F.trim("product_name")).distinct()
C.write_parquet(df, args["trusted_path"])
print(f"[aish-sim] trusted/pos rows: {df.count()} · cust_num type: {dict(df.dtypes)['cust_num']}")
