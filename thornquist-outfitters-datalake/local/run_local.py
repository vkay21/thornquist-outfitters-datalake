"""
Run the whole Thornquist pipeline on a laptop (no AWS needed) for testing and evidence.

    pip install pyspark==3.5.* duckdb pandas pyarrow matplotlib     # Java 17 required
    python local/run_local.py --sample-dir path/to/Project1_Thornquist_Outfitters_SampleData

It builds ./local_lake/{landing,raw,trusted,quarantine,dq_reports,curated}, runs the
four Glue job scripts unchanged, then runs every sql/analytics/*.sql query with DuckDB
against the curated Parquet (same table names as Athena) and saves the results to
evidence/local_run/.
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS = os.path.join(ROOT, "glue_jobs")


def run_job(script, **kw):
    cmd = [sys.executable, os.path.join(JOBS, script)]
    for k, v in kw.items():
        cmd += [f"--{k}", str(v)]
    print(f"\n=== {script} ===", flush=True)
    res = subprocess.run(cmd, capture_output=True, text=True)
    out = "\n".join(l for l in (res.stdout + res.stderr).splitlines()
                    if l.startswith(("[dq]", "[metrics]", "[curated]", "[schema]", "Traceback")) or "Error" in l)
    print(out)
    return res.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample-dir", required=True)
    ap.add_argument("--lake", default=os.path.join(ROOT, "local_lake"))
    ap.add_argument("--batch-id", default="local-run-001")
    ap.add_argument("--pos-mode", choices=["gate", "aish"], default="gate",
                    help="gate = thornquist-pos-dq-gate · aish = Aish's thornquist-pos-raw-to-trusted (simulated)")
    a = ap.parse_args()
    lake = a.lake
    shutil.rmtree(lake, ignore_errors=True)

    # landing -> raw (in AWS this is Aish's ingestion layer; locally just a copy)
    layout = {
        "pos": "pos_sales_*.csv",
        "ecommerce": "ecommerce_orders*.json",
        "customer": "customer_extract*.csv",
    }
    for src, pattern in layout.items():
        for zone in ("landing", "raw"):
            d = os.path.join(lake, zone, src, "ingest_date=2026-08-31")
            os.makedirs(d, exist_ok=True)
            for f in glob.glob(os.path.join(a.sample_dir, pattern)):
                shutil.copy(f, d)

    p = lambda *x: os.path.join(lake, *x)  # noqa: E731
    common = {"batch_id": a.batch_id}
    rc = run_job("raw_to_trusted_customer.py", raw_path=p("raw", "customer"), trusted_path=p("trusted", "customer"),
                 quarantine_path=p("quarantine", "customer"), report_path=p("dq_reports", "customer"), **common)
    if a.pos_mode == "gate":
        rc |= run_job("raw_to_trusted_pos.py", raw_path=p("raw", "pos"), trusted_customers_path=p("trusted", "customer"),
                      trusted_path=p("trusted", "pos"), quarantine_path=p("quarantine", "pos"),
                      report_path=p("dq_reports", "pos"), **common)
    else:  # Aish's job, simulated from her description
        print("\n=== simulate_aish_pos.py (POS_MODE=aish) ===")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "local", "simulate_aish_pos.py"),
                            "--raw_path", p("raw", "pos"), "--trusted_path", p("trusted", "pos")],
                           capture_output=True, text=True)
        print("\n".join(l for l in (r.stdout + r.stderr).splitlines() if l.startswith("[aish-sim]") or "Error" in l))
        rc |= r.returncode
    rc |= run_job("raw_to_trusted_ecommerce.py", raw_path=p("raw", "ecommerce"),
                  trusted_customers_path=p("trusted", "customer"), trusted_path=p("trusted", "ecommerce"),
                  quarantine_path=p("quarantine", "ecommerce"), report_path=p("dq_reports", "ecommerce"), **common)
    rc |= run_job("trusted_to_curated.py", pos_path=p("trusted", "pos"), ecommerce_path=p("trusted", "ecommerce"),
                  customers_path=p("trusted", "customer"), curated_path=p("curated"))
    if rc:
        sys.exit("A job failed - see output above")

    run_queries(lake)


def register_duckdb(lake):
    import duckdb

    con = duckdb.connect()
    con.execute("CREATE SCHEMA IF NOT EXISTS thornquist_curated")
    con.execute("CREATE SCHEMA IF NOT EXISTS thornquist_trusted")
    con.execute("CREATE SCHEMA IF NOT EXISTS thornquist_quarantine")
    views = {
        "thornquist_curated.fact_sales": ("curated/fact_sales/*/*/*.parquet", True),
        "thornquist_curated.dim_customer": ("curated/dim_customer/*.parquet", False),
        "thornquist_curated.agg_daily_sales": ("curated/agg_daily_sales/*.parquet", False),
        "thornquist_trusted.pos": ("trusted/pos/**/*.parquet", True),
        "thornquist_trusted.ecommerce": ("trusted/ecommerce/*/*.parquet", True),
        "thornquist_quarantine.pos": ("quarantine/pos/*/*.parquet", True),
        "thornquist_quarantine.ecommerce": ("quarantine/ecommerce/*/*.parquet", True),
    }
    for name, (pattern, hive) in views.items():
        path = os.path.join(lake, pattern)
        if not glob.glob(path):
            continue
        opts = ", hive_partitioning = true, hive_types_autocast = false" if hive else ""
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{path}'{opts})")
    return con


def run_queries(lake):
    con = register_duckdb(lake)
    out_dir = os.path.join(ROOT, "evidence", "local_run")
    os.makedirs(out_dir, exist_ok=True)
    md = ["# Local run - Athena query results (executed with DuckDB on the curated Parquet)\n"]
    for f in sorted(glob.glob(os.path.join(ROOT, "sql", "analytics", "*.sql"))):
        sql = open(f).read()
        name = os.path.basename(f)[:-4]
        df = con.execute(sql).fetchdf()
        df.to_csv(os.path.join(out_dir, f"{name}.csv"), index=False)
        title = next((l[2:].strip() for l in sql.splitlines() if l.startswith("--")), name)
        md += [f"\n## {name}\n", f"_{title}_\n", df.to_markdown(index=False), ""]
        print(f"\n--- {name} ({len(df)} rows)\n{df.head(12).to_string(index=False)}")
    for src in ("customer", "pos", "ecommerce"):
        for rep in glob.glob(os.path.join(lake, "dq_reports", src, "*", "dq_report.json")):
            shutil.copy(rep, os.path.join(out_dir, f"dq_report_{src}.json"))
    with open(os.path.join(out_dir, "query_results.md"), "w") as fh:
        fh.write("\n".join(md))
    print(f"\nResults written to {out_dir}")


if __name__ == "__main__":
    main()
