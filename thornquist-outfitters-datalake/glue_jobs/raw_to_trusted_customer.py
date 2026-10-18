"""
Glue job: thornquist-customer-raw-to-trusted
Raw weekly customer extract (CSV flat file) -> DQ gate -> trusted/customer (Parquet)

Runs FIRST in the workflow: trusted/customer is the reference set that the POS and
e-commerce jobs use for their referential-integrity rule.

Arguments
  --raw_path         s3://<bucket>/raw/customer/            (CSV, header row)
  --trusted_path     s3://<bucket>/trusted/customer/
  --quarantine_path  s3://<bucket>/quarantine/customer/
  --report_path      s3://<bucket>/dq_reports/customer/
  --max_reject_pct   optional, default 5
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

from pyspark.sql import functions as F
from pyspark.sql import types as T

import tq_common as C
from tq_dq import FLAG, REJECT, Rule, add_remediation, duplicate_rank, run_gate

args = C.get_args(
    ["raw_path", "trusted_path", "quarantine_path", "report_path"],
    {"max_reject_pct": "5"},
)
ctx = C.JobContext(args)
spark = ctx.spark

# Read EVERYTHING as string: the legacy system zero-pads IDs and a crawler would
# otherwise infer bigint and silently strip them (schema conflict C2).
schema = T.StructType([T.StructField(c, T.StringType()) for c in
                       ["cust_num", "first_name", "last_name", "email", "signup_date", "loyalty_tier", "region"]])
raw = (
    spark.read.option("header", "true").schema(schema).csv(args["raw_path"])
    .withColumn("_source_file", F.input_file_name())
    .withColumn("_ingest_seq", F.monotonically_increasing_id())
)

# ---- Remediation (deterministic, logged) ---------------------------------------
df = raw
for c in ["cust_num", "first_name", "last_name", "email", "loyalty_tier", "region", "signup_date"]:
    cleaned = F.trim(F.regexp_replace(F.col(c), " ", " "))
    df = add_remediation(df, F.col(c) != cleaned, f"trimmed_whitespace:{c}")
    df = df.withColumn(c, cleaned)
df = df.withColumn("email", F.lower("email"))
df = df.withColumn("signup_date_parsed", F.coalesce(F.to_date("signup_date", "yyyy-MM-dd"), F.to_date("signup_date", "dd/MM/yyyy")))
df = add_remediation(df, F.col("signup_date").rlike(r"^\d{2}/\d{2}/\d{4}$"), "date_reformatted:signup_date")
df = df.withColumn("_dup_rank", duplicate_rank(["cust_num"]))

rules = [
    Rule("CUS-01", "cust_num present and 6 digits", "completeness", REJECT,
         F.col("cust_num").isNull() | ~F.col("cust_num").rlike(r"^\d{6}$"),
         "Primary key must exist and match the legacy 6-digit format."),
    Rule("CUS-02", "cust_num unique", "uniqueness", REJECT, F.col("_dup_rank") > 1,
         "Second and later copies of a customer number are quarantined; first copy wins."),
    Rule("CUS-03", "signup_date valid and not in future", "validity", REJECT,
         F.col("signup_date_parsed").isNull() | (F.col("signup_date_parsed") > F.current_date())
         | (F.col("signup_date_parsed") < F.lit("2000-01-01").cast("date")),
         "Unparseable or impossible sign-up dates."),
    Rule("CUS-04", "loyalty_tier in reference domain", "validity", REJECT,
         ~F.col("loyalty_tier").isin(C.VALID_LOYALTY_TIERS) | F.col("loyalty_tier").isNull(),
         f"Allowed: {C.VALID_LOYALTY_TIERS}"),
    Rule("CUS-05", "email well-formed", "validity", FLAG,
         F.col("email").isNull() | ~F.col("email").rlike(r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
         "Bad emails do not block analytics, so the row is promoted with a flag."),
    Rule("CUS-06", "region in reference domain", "validity", FLAG,
         ~F.col("region").isin(C.VALID_REGIONS) | F.col("region").isNull(),
         f"Allowed: {C.VALID_REGIONS}"),
]

promotable, report = run_gate(
    df, rules, source="customer", batch_id=args["batch_id"], max_reject_pct=float(args["max_reject_pct"]),
    quarantine_path=args["quarantine_path"], report_path=args["report_path"],
    write_parquet=C.write_parquet, write_json_report=C.write_json_report,
)

trusted = promotable.select(
    "cust_num", "first_name", "last_name", "email",
    F.col("signup_date_parsed").alias("signup_date"),
    "loyalty_tier",
    F.col("region").alias("home_region"),
    "dq_flags", "dq_remediations",
    F.lit(args["batch_id"]).alias("dq_batch_id"),
    F.current_timestamp().alias("_loaded_at"),
)
# Weekly full snapshot -> overwrite (SCD type 1 for this first-generation lake).
C.write_parquet(trusted, args["trusted_path"], mode="overwrite")
C.publish_metrics("customer", {k: report[k] for k in ("rows_checked", "rows_promoted", "rows_quarantined")})
ctx.commit()
