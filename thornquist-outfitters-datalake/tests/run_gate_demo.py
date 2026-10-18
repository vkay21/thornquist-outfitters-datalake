"""
Demonstrates the quality gate on deliberately broken input (Week-2 milestone evidence):

  1. POS bad batch      -> 8 of 11 rows rejected, threshold breached, batch HELD_BACK (job fails)
  2. Same batch, lenient threshold (--max_reject_pct 100) -> good rows promoted, bad rows quarantined
  3. E-commerce v2 file with new fields (promo_code, gift_wrap) -> pipeline keeps working,
     new fields preserved in extra_attributes; bad orders quarantined

Requires a prior `python local/run_local.py ...` so trusted/customers exists.
    python tests/run_gate_demo.py
"""
import glob
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAKE = os.path.join(ROOT, "local_lake")
DEMO = os.path.join(LAKE, "_gate_demo")
FIX = os.path.join(ROOT, "tests", "fixtures")
OUT = os.path.join(ROOT, "evidence", "gate_demo")


def job(script, **kw):
    cmd = [sys.executable, os.path.join(ROOT, "glue_jobs", script)] + sum([[f"--{k}", str(v)] for k, v in kw.items()], [])
    r = subprocess.run(cmd, capture_output=True, text=True)
    lines = [l for l in (r.stdout + r.stderr).splitlines() if l.startswith(("[dq]", "[schema]")) or "BatchRejected" in l]
    print("\n".join(lines))
    print(f"exit code: {r.returncode} ({'FAILED - Glue would mark run as FAILED' if r.returncode else 'SUCCEEDED'})")
    return r.returncode


def main():
    shutil.rmtree(DEMO, ignore_errors=True)
    os.makedirs(OUT, exist_ok=True)
    cust = os.path.join(LAKE, "trusted", "customers")
    if not os.path.exists(cust):
        sys.exit("Run local/run_local.py first")
    os.makedirs(os.path.join(DEMO, "raw", "pos"))
    os.makedirs(os.path.join(DEMO, "raw", "ecommerce"))
    shutil.copy(os.path.join(FIX, "pos_sales_bad_batch.csv"), os.path.join(DEMO, "raw", "pos"))
    shutil.copy(os.path.join(FIX, "ecommerce_orders_schema_v2.json"), os.path.join(DEMO, "raw", "ecommerce"))
    d = lambda *p: os.path.join(DEMO, *p)  # noqa: E731

    print("\n### 1. POS bad batch, default 5% threshold")
    job("raw_to_trusted_pos.py", raw_path=d("raw", "pos"), trusted_customers_path=cust, trusted_path=d("trusted", "pos_sales"),
        quarantine_path=d("quarantine", "pos"), report_path=d("dq_reports", "pos"), batch_id="bad-batch-strict")
    print("trusted written?", os.path.exists(d("trusted", "pos_sales")))

    print("\n### 2. Same batch, threshold 100% (row-level quarantine only)")
    job("raw_to_trusted_pos.py", raw_path=d("raw", "pos"), trusted_customers_path=cust, trusted_path=d("trusted", "pos_sales"),
        quarantine_path=d("quarantine", "pos"), report_path=d("dq_reports", "pos"), batch_id="bad-batch-lenient",
        max_reject_pct=100)

    print("\n### 3. E-commerce schema v2 (new attributes) + bad orders")
    job("raw_to_trusted_ecommerce.py", raw_path=d("raw", "ecommerce"), trusted_customers_path=cust,
        trusted_path=d("trusted", "ecommerce_order_lines"), quarantine_path=d("quarantine", "ecommerce"),
        report_path=d("dq_reports", "ecommerce"), batch_id="schema-v2", max_reject_pct=100)

    import duckdb

    con = duckdb.connect()
    q = con.execute(f"""SELECT transaction_id, sale_date, product_name, quantity, unit_price, region, payment_method,
                              cust_num, dq_failed_rules FROM read_parquet('{d('quarantine','pos','batch_id=bad-batch-lenient','*.parquet')}')
                       ORDER BY transaction_id""").fetchdf()
    t = con.execute(f"""SELECT transaction_id, sale_date, product_name, cust_num, is_walk_in, is_orphan_customer, dq_flags,
                              dq_remediations FROM read_parquet('{d('trusted','pos_sales','*','*.parquet')}', hive_partitioning=true)
                       ORDER BY transaction_id""").fetchdf()
    e = con.execute(f"""SELECT order_id, channel, sku, category, quantity, line_revenue, extra_attributes
                       FROM read_parquet('{d('trusted','ecommerce_order_lines','*','*.parquet')}', hive_partitioning=true)""").fetchdf()
    eq = con.execute(f"""SELECT order_id, order_timestamp, order_total, dq_failed_rules
                        FROM read_parquet('{d('quarantine','ecommerce','*','*.parquet')}')""").fetchdf()
    md = ["# Quality-gate demonstration (deliberately broken input)\n",
          "## POS bad batch - strict run\n", "```json", open(glob.glob(d("dq_reports", "pos", "batch_id=bad-batch-strict", "*.json"))[0]).read(), "```",
          "\n## POS bad batch - quarantined rows (lenient run)\n", q.to_markdown(index=False),
          "\n## POS bad batch - promoted rows (lenient run)\n", t.to_markdown(index=False),
          "\n## E-commerce schema v2 - promoted lines (new fields kept in extra_attributes)\n", e.to_markdown(index=False),
          "\n## E-commerce schema v2 - quarantined orders\n", eq.to_markdown(index=False)]
    open(os.path.join(OUT, "gate_demo_results.md"), "w").write("\n".join(md))
    print("\nQuarantined POS rows:\n", q.to_string(index=False))
    print("\nPromoted POS rows:\n", t.to_string(index=False))
    print("\nPromoted e-com lines:\n", e.to_string(index=False))
    print("\nQuarantined e-com orders:\n", eq.to_string(index=False))


if __name__ == "__main__":
    main()
