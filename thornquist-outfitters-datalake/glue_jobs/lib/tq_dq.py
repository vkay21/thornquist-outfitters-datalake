"""
tq_dq.py - the Thornquist data-quality gate.

Every rule is declared as data (name, dimension, action, failing-condition), so the
rule catalogue in data_quality/dq_rules.md maps 1:1 onto code.

Actions
-------
REJECT  -> row is written to quarantine/ and NOT promoted to trusted/.
FLAG    -> row IS promoted, but carries the rule name in dq_flags so analysts can
           filter it; it is also counted in the DQ report for data-steward review.

Remediations (deterministic fixes such as re-formatting a DD/MM/YYYY date or trimming
a non-breaking space) are not failures: they are applied before the rules run and
recorded per row in dq_remediations, so every change made to source data is auditable.

Batch gate
----------
If the share of REJECTED rows in a batch exceeds max_reject_pct, the whole batch is
held back: nothing is promoted, the quarantine + report are still written, and the
job raises so Glue marks the run FAILED (-> CloudWatch alarm / EventBridge).
"""
from dataclasses import dataclass

from pyspark.sql import Window
from pyspark.sql import functions as F

REJECT = "REJECT"
FLAG = "FLAG"


@dataclass
class Rule:
    rule_id: str
    name: str
    dimension: str  # completeness | uniqueness | validity | range | referential_integrity | consistency
    action: str  # REJECT | FLAG
    fails: object  # pyspark Column: True when the row FAILS the rule
    description: str = ""


class BatchRejected(Exception):
    pass


def duplicate_rank(key_cols, order_col="_ingest_seq"):
    """1 for the first occurrence of a key, 2+ for repeats (webhook retry / batch resend)."""
    w = Window.partitionBy(*key_cols).orderBy(F.col(order_col))
    return F.row_number().over(w)


def add_remediation(df, condition, label):
    """Append `label` to dq_remediations wherever `condition` is true."""
    if "dq_remediations" not in df.columns:
        df = df.withColumn("dq_remediations", F.array().cast("array<string>"))
    return df.withColumn(
        "dq_remediations",
        F.when(F.coalesce(condition, F.lit(False)), F.array_union("dq_remediations", F.array(F.lit(label)))).otherwise(
            F.col("dq_remediations")
        ),
    )


def apply_rules(df, rules):
    """Evaluate all rules; adds dq_failed_rules, dq_flags, dq_status."""
    if "dq_remediations" not in df.columns:
        df = df.withColumn("dq_remediations", F.array().cast("array<string>"))
    failed = F.array(*[F.when(F.coalesce(r.fails, F.lit(False)), F.lit(r.rule_id)) for r in rules])
    df = df.withColumn("dq_failed_rules", F.filter(failed, lambda x: x.isNotNull()))
    reject_ids = F.array(*[F.lit(r.rule_id) for r in rules if r.action == REJECT])
    flag_ids = F.array(*[F.lit(r.rule_id) for r in rules if r.action == FLAG] or [F.lit("__none__")])
    df = df.withColumn("dq_flags", F.array_intersect("dq_failed_rules", flag_ids))
    df = df.withColumn(
        "dq_status",
        F.when(F.size(F.array_intersect("dq_failed_rules", reject_ids)) > 0, F.lit("QUARANTINE"))
        .when(F.size("dq_flags") > 0, F.lit("PROMOTE_FLAGGED"))
        .otherwise(F.lit("PROMOTE")),
    )
    return df


def summarise(df, rules, source, batch_id, max_reject_pct):
    """Build the per-batch DQ report (one Spark action)."""
    aggs = [F.count(F.lit(1)).alias("rows_checked")]
    aggs += [F.sum(F.when(F.array_contains("dq_failed_rules", r.rule_id), 1).otherwise(0)).alias(r.rule_id) for r in rules]
    aggs += [
        F.sum(F.when(F.col("dq_status") == s, 1).otherwise(0)).alias(s)
        for s in ("PROMOTE", "PROMOTE_FLAGGED", "QUARANTINE")
    ]
    aggs.append(F.collect_list("dq_remediations").alias("_rem"))
    row = df.agg(*aggs).collect()[0].asDict()
    rem_counts = {}
    for arr in row.pop("_rem") or []:
        for label in arr or []:
            rem_counts[label] = rem_counts.get(label, 0) + 1
    checked = row["rows_checked"] or 0
    reject_pct = round(100.0 * (row["QUARANTINE"] or 0) / checked, 2) if checked else 0.0
    report = {
        "source": source,
        "batch_id": batch_id,
        "rows_checked": checked,
        "rows_promoted": row["PROMOTE"] + row["PROMOTE_FLAGGED"],
        "rows_promoted_flagged": row["PROMOTE_FLAGGED"],
        "rows_quarantined": row["QUARANTINE"],
        "reject_pct": reject_pct,
        "max_reject_pct": max_reject_pct,
        "batch_decision": "PROMOTED" if reject_pct <= max_reject_pct else "HELD_BACK",
        "remediations_applied": rem_counts,
        "rules": [
            {
                "rule_id": r.rule_id,
                "name": r.name,
                "dimension": r.dimension,
                "action": r.action,
                "failed_rows": row[r.rule_id],
                "status": "PASS" if row[r.rule_id] == 0 else ("FAIL" if r.action == REJECT else "WARN"),
                "description": r.description,
            }
            for r in rules
        ],
    }
    return report


def run_gate(df, rules, *, source, batch_id, max_reject_pct, quarantine_path, report_path, write_parquet, write_json_report):
    """Apply rules, write quarantine + report, return the promotable DataFrame.

    Raises BatchRejected (after writing evidence) if the batch breaches the threshold.
    """
    checked = apply_rules(df, rules).cache()
    report = summarise(checked, rules, source, batch_id, max_reject_pct)

    quarantined = checked.filter(F.col("dq_status") == "QUARANTINE").withColumn("dq_batch_id", F.lit(batch_id))
    if report["rows_quarantined"] > 0:
        write_parquet(quarantined.drop("_ingest_seq"), f"{quarantine_path.rstrip('/')}/batch_id={batch_id}", mode="overwrite")
    write_json_report(f"{report_path.rstrip('/')}/batch_id={batch_id}/dq_report.json", report)

    print(f"[dq] {source}: {report['rows_checked']} checked, {report['rows_promoted']} promoted "
          f"({report['rows_promoted_flagged']} flagged), {report['rows_quarantined']} quarantined "
          f"-> {report['batch_decision']}")
    for r in report["rules"]:
        print(f"[dq]   {r['rule_id']:<8} {r['status']:<4} {r['failed_rows']:>5}  {r['name']}")

    if report["batch_decision"] == "HELD_BACK":
        raise BatchRejected(
            f"{source} batch {batch_id}: {report['reject_pct']}% rejected > threshold {max_reject_pct}% - nothing promoted"
        )
    promotable = checked.filter(F.col("dq_status") != "QUARANTINE").drop("dq_failed_rules", "dq_status")
    return promotable, report
