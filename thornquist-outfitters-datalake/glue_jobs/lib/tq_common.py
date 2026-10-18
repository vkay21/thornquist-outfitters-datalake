"""
tq_common.py - shared helpers for every Thornquist Glue job.

The same job scripts run in two places:
  * AWS Glue (Glue 4.0/5.0, PySpark) - arguments come from getResolvedOptions,
    paths are s3:// URIs, metrics go to CloudWatch.
  * A laptop / CI box (plain PySpark) - arguments come from --key value pairs,
    paths are local folders, metrics are just printed.

Uploaded to S3 and attached to each job with --extra-py-files.
"""
import json
import os
import sys
from datetime import datetime, timezone

try:  # Running inside AWS Glue
    from awsglue.context import GlueContext
    from awsglue.job import Job
    from awsglue.utils import getResolvedOptions
    from pyspark.context import SparkContext

    IN_GLUE = True
except ImportError:  # Running locally
    IN_GLUE = False

from pyspark.sql import SparkSession

# Reference domains shared by all rules (single source of truth).
VALID_REGIONS = ["Ontario", "Quebec", "Alberta", "British Columbia", "Atlantic"]
VALID_CATEGORIES = ["Apparel", "Footwear", "Camping", "Accessories"]
VALID_PAYMENT_METHODS = ["VISA", "MASTERCARD", "AMEX", "DEBIT", "GIFT_CARD"]
VALID_LOYALTY_TIERS = ["Standard", "Silver", "Gold"]
VALID_ECOM_CHANNELS = ["online", "app"]
# E-commerce SKU prefix -> POS category name (schema conflict C3).
SKU_PREFIX_TO_CATEGORY = {"APP": "Apparel", "FOO": "Footwear", "CAM": "Camping", "ACC": "Accessories"}
WALK_IN_PLACEHOLDER = "0000000"
BUSINESS_TIMEZONE = "America/Toronto"  # head-office day boundary (schema conflict C5)
CURRENCY = "CAD"


def get_args(required, optional=None):
    """Return a dict of job arguments, identical behaviour in Glue and locally."""
    optional = optional or {}
    argv = sys.argv
    if IN_GLUE:
        present = [k for k in optional if f"--{k}" in argv]
        args = getResolvedOptions(argv, ["JOB_NAME"] + list(required) + present)
    else:
        args = {"JOB_NAME": "local"}
        for i, tok in enumerate(argv):
            if tok.startswith("--") and i + 1 < len(argv):
                args[tok[2:]] = argv[i + 1]
        missing = [k for k in required if k not in args]
        if missing:
            raise SystemExit(f"Missing required arguments: {missing}")
    for k, v in optional.items():
        args.setdefault(k, v)
    args.setdefault("batch_id", datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    return args


class JobContext:
    """Wraps SparkSession (+ Glue Job bookkeeping when in Glue)."""

    def __init__(self, args):
        self.args = args
        if IN_GLUE:
            sc = SparkContext.getOrCreate()
            self.glue_context = GlueContext(sc)
            self.spark = self.glue_context.spark_session
            self.job = Job(self.glue_context)
            self.job.init(args["JOB_NAME"], args)
        else:
            self.spark = (
                SparkSession.builder.master("local[*]")
                .appName(args.get("JOB_NAME", "local"))
                .config("spark.sql.shuffle.partitions", "4")
                .config("spark.ui.enabled", "false")
                .getOrCreate()
            )
            self.spark.sparkContext.setLogLevel("ERROR")
        # All timestamps handled in UTC; business dates derived explicitly.
        self.spark.conf.set("spark.sql.session.timeZone", "UTC")
        # Glue 4.0/5.0 run non-ANSI: a bad date parses to NULL (caught by a DQ rule)
        # instead of killing the job. Pin it so local Spark 4 behaves the same way.
        self.spark.conf.set("spark.sql.ansi.enabled", "false")
        # Overwrite only the partitions a run touches (idempotent re-runs).
        self.spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")

    def commit(self):
        if IN_GLUE:
            self.job.commit()


def join_path(base, *parts):
    return "/".join([base.rstrip("/")] + [p.strip("/") for p in parts])


def write_parquet(df, path, partition_cols=None, mode="overwrite"):
    writer = df.write.mode(mode).option("compression", "snappy")
    if partition_cols:
        writer = writer.partitionBy(*partition_cols)
    writer.parquet(path)


def write_json_report(path, payload):
    """Write a small JSON document (DQ report) to S3 or local disk."""
    # Single-line JSON so Athena's JSON SerDe can read reports as a table (sql/ddl/04_dq_reports.sql).
    body = json.dumps(payload, default=str)
    if path.startswith("s3://"):
        import boto3

        bucket, key = path[5:].split("/", 1)
        boto3.client("s3").put_object(Bucket=bucket, Key=key, Body=body.encode(), ContentType="application/json")
    else:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(body)


def publish_metrics(source, metrics, namespace="Thornquist/DataQuality"):
    """Push DQ counts to CloudWatch so an alarm can fire on quarantine spikes."""
    print(f"[metrics] {source}: {json.dumps(metrics)}")
    if not IN_GLUE:
        return
    try:
        import boto3

        cw = boto3.client("cloudwatch")
        cw.put_metric_data(
            Namespace=namespace,
            MetricData=[
                {"MetricName": k, "Dimensions": [{"Name": "Source", "Value": source}], "Value": float(v), "Unit": "Count"}
                for k, v in metrics.items()
                if isinstance(v, (int, float))
            ],
        )
    except Exception as exc:  # metrics must never break the pipeline
        print(f"[metrics] CloudWatch publish skipped: {exc}")
