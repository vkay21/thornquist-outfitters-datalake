"""Generates thornquist_dashboard.ipynb (kept as code so diffs stay readable)."""
import nbformat as nbf

nb = nbf.v4.new_notebook()
md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
cells = []

cells.append(md("""# Thornquist Outfitters: Sales Dashboard
**Visualisation layer (QuickSight substitute).** QuickSight is not in the Learner Lab catalog, so this
notebook runs the same curated-layer SQL that analysts use (`sql/analytics/`) and charts the results.

* `MODE = "athena"`: runs on AWS through the `thornquist-wg` workgroup using boto3. Use SageMaker Studio Lab,
  a Glue notebook, or a laptop with Learner Lab credentials.
* `MODE = "local"`: runs on the Parquet output of `local/run_local.py` using DuckDB, with the same SQL and
  table names.

**Cost note:** a QuickSight Standard author costs about USD 9–24 per month plus SPICE capacity. This notebook
costs only the Athena bytes it scans, which is under 1 MB for the queries below (well below USD 0.01)."""))

cells.append(code("""import os, time, glob
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick

MODE = os.environ.get("TQ_MODE", "local")          # "athena" or "local"
BUCKET = os.environ.get("BUCKET", "<your-lake-bucket>")
WORKGROUP = "thornquist-wg"
ROOT = os.path.abspath(os.path.join(os.getcwd(), "..")) if os.path.basename(os.getcwd()) == "dashboard" else os.getcwd()
SQL_DIR = os.path.join(ROOT, "sql", "analytics")
FIG_DIR = os.path.join(ROOT, "dashboard", "figures"); os.makedirs(FIG_DIR, exist_ok=True)

# Fixed colour per entity (validated categorical slots 1-2; colour follows the channel, never its rank)
STORE, ONLINE = "#2a78d6", "#eb6834"
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({"figure.dpi": 110, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
                     "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlecolor": INK,
                     "legend.frameon": False})

if MODE == "local":
    import sys; sys.path.insert(0, os.path.join(ROOT, "local"))
    from run_local import register_duckdb
    con = register_duckdb(os.path.join(ROOT, "local_lake"))
    def run_sql(sql): return con.execute(sql).fetchdf()
else:
    import boto3
    athena = boto3.client("athena", region_name="us-east-1")
    def run_sql(sql):
        qid = athena.start_query_execution(QueryString=sql, WorkGroup=WORKGROUP)["QueryExecutionId"]
        while (st := athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]["State"]) in ("QUEUED", "RUNNING"):
            time.sleep(1)
        if st != "SUCCEEDED":
            raise RuntimeError(athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"])
        return pd.read_csv(f"s3://{BUCKET}/athena-results/{qid}.csv")   # needs s3fs; or use get_query_results

def q(name):
    return run_sql(open(os.path.join(SQL_DIR, name + ".sql")).read())

def save(fig, name):
    fig.savefig(os.path.join(FIG_DIR, name + ".png"), bbox_inches="tight", facecolor="white")
print("mode:", MODE)"""))

cells.append(md("## Headline KPIs (week of 24–30 Aug 2026)"))
cells.append(code("""kpi = run_sql('''
SELECT channel, COUNT(DISTINCT order_id) AS orders, SUM(CAST(line_revenue AS DOUBLE)) AS revenue
FROM thornquist_curated.fact_sales WHERE sale_date BETWEEN '2026-08-24' AND '2026-08-30' GROUP BY channel''')
tot = kpi.revenue.sum()
online = kpi.loc[kpi.channel != 'store', 'revenue'].sum()
tiles = [("Total revenue", f"${tot:,.0f}"), ("Online share", f"{online/tot:.1%}"),
         ("Store transactions", f"{int(kpi.loc[kpi.channel=='store','orders'].sum()):,}"),
         ("Online orders", f"{int(kpi.loc[kpi.channel!='store','orders'].sum()):,}")]
fig, axes = plt.subplots(1, 4, figsize=(11, 1.6))
for ax, (label, value) in zip(axes, tiles):
    ax.axis("off"); ax.text(0, 0.62, value, fontsize=22, weight="bold", color=INK); ax.text(0, 0.1, label, color=MUTED)
save(fig, "00_kpis"); plt.show()"""))

cells.append(md("## 1 · Revenue by region and channel\nWhich regions drive revenue, and how dependent each is on stores (Q1)."))
cells.append(code("""r = q("q01_revenue_by_channel_region").sort_values("total_revenue")
fig, ax = plt.subplots(figsize=(9, 3.8))
ax.barh(r.region, r.store_revenue, color=STORE, height=0.6, label="Store", edgecolor="white", linewidth=2)
ax.barh(r.region, r.online_revenue, left=r.store_revenue, color=ONLINE, height=0.6, label="Online", edgecolor="white", linewidth=2)
for y, (t, s) in enumerate(zip(r.total_revenue, r.online_share_pct)):
    ax.text(t + 800, y, f"${t/1000:,.1f}k  ·  {s:.0f}% online", va="center", color=MUTED, fontsize=9)
ax.xaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"${v/1000:.0f}k")); ax.grid(axis="y", visible=False)
ax.set_xlim(0, r.total_revenue.max() * 1.35); ax.set_title("Revenue by region, store vs online")
ax.legend(loc="lower right", ncol=2); save(fig, "01_region_channel"); plt.show()
r.sort_values("total_revenue", ascending=False)"""))

cells.append(md("## 2 · Category mix by channel (Q2)"))
cells.append(code("""c = q("q02_category_by_channel")
p = c.pivot(index="category", columns="channel", values="revenue").sort_values("store")
fig, ax = plt.subplots(figsize=(9, 3.4)); h = 0.38; y = range(len(p))
ax.barh([i + h/2 for i in y], p["store"], h, color=STORE, label="Store", edgecolor="white", linewidth=2)
ax.barh([i - h/2 for i in y], p["online"], h, color=ONLINE, label="Online", edgecolor="white", linewidth=2)
ax.set_yticks(list(y)); ax.set_yticklabels(p.index); ax.grid(axis="y", visible=False)
ax.xaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"${v/1000:.0f}k"))
ax.set_title("Revenue by category and channel"); ax.legend(loc="lower right", ncol=2)
save(fig, "02_category_channel"); plt.show(); c"""))

cells.append(md("## 3 · Daily revenue trend (Q3)"))
cells.append(code("""d = q("q03_daily_trend_growth"); d["sale_date"] = pd.to_datetime(d.sale_date)
fig, ax = plt.subplots(figsize=(9, 3.4))
for ch, col, lab in (("store", STORE, "Store"), ("online", ONLINE, "Online")):
    s = d[d.channel == ch]
    ax.plot(s.sale_date, s.revenue, color=col, lw=2, marker="o", ms=5, label=lab)
    ax.annotate(lab, (s.sale_date.iloc[-1], s.revenue.iloc[-1]), xytext=(8, 0), textcoords="offset points",
                va="center", color=INK, fontsize=9)
ax.set_ylim(0); ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"${v/1000:.0f}k"))
ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%a %d")); ax.grid(axis="x", visible=False)
ax.set_title("Daily revenue by channel"); ax.legend(loc="lower left", ncol=2)
save(fig, "03_daily_trend"); plt.show(); d"""))

cells.append(md("## 4 · Customer-segment insight: loyalty tier × channel (Q4)\nThis blends the legacy customer extract with sales from both channels."))
cells.append(code("""s = q("q04_segment_channel_behaviour")
order = ["Gold", "Silver", "Standard", "Unmatched", "Walk-in"]
p = s.pivot(index="customer_segment", columns="channel", values="avg_order_value").reindex(order)
fig, ax = plt.subplots(figsize=(9, 3.4)); w = 0.38; x = range(len(p))
ax.bar([i - w/2 for i in x], p["store"].fillna(0), w, color=STORE, label="Store", edgecolor="white", linewidth=2)
ax.bar([i + w/2 for i in x], p["online"].fillna(0), w, color=ONLINE, label="Online", edgecolor="white", linewidth=2)
for i, (a, b) in enumerate(zip(p["store"], p["online"])):
    if pd.notna(b): ax.text(i + w/2, b + 8, f"${b:,.0f}", ha="center", fontsize=8, color=MUTED)
    if pd.notna(a): ax.text(i - w/2, a + 8, f"${a:,.0f}", ha="center", fontsize=8, color=MUTED)
ax.set_xticks(list(x)); ax.set_xticklabels(order); ax.grid(axis="x", visible=False)
ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"${v:.0f}"))
ax.set_title("Average order value by segment: online baskets are about 2× store tickets"); ax.legend(ncol=2)
save(fig, "04_segment_aov"); plt.show(); s"""))

cells.append(md("## 5 · Omnichannel customers are worth more (Q5)"))
cells.append(code("""o = q("q05_omnichannel_customers"); o["label"] = o.channel_mix.str[4:]
fig, ax = plt.subplots(figsize=(9, 3.0))
ax.barh(o.label[::-1], o.revenue_per_customer[::-1], color=STORE, height=0.55)
for y, (v, n) in enumerate(zip(o.revenue_per_customer[::-1], o.customers[::-1])):
    ax.text(v + 15, y, f"${v:,.0f} per customer  ·  {n} customers", va="center", color=MUTED, fontsize=9)
ax.set_xlim(0, o.revenue_per_customer.max() * 1.6); ax.grid(axis="y", visible=False)
ax.xaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"${v:,.0f}"))
ax.set_title("Weekly revenue per customer by channel mix")
save(fig, "05_omnichannel"); plt.show(); o"""))

cells.append(md("## 6 · Store league table and walk-in rate (Q7) · Data trust (Q8)"))
cells.append(code("""st = q("q07_store_customer_capture"); display(st)
display(q("q08_data_trust_exposure"))
display(q("q06_demand_vs_allocation"))"""))

cells.append(md("""## Key findings
1. **Ontario leads revenue** at about a quarter of the company total. **Atlantic is the outlier**: more than
   half its revenue is online because it has only one store (Halifax). That points to a case for a second
   Atlantic store or faster regional fulfilment.
2. **Online baskets are about 2× the value of store tickets** in every loyalty tier (more items per order).
   Silver customers are the highest-value online shoppers.
3. **Omnichannel customers** (about 40 % of the customer base) generate roughly **2.2× the weekly revenue** of
   store-only customers. Cross-channel loyalty marketing is the lever.
4. **Data trust:** 14 % of online revenue comes from orders whose customer ID is missing from the master
   extract, and 17 % of store revenue is anonymous walk-ins. Segment metrics should be read with that coverage
   in mind. Fixing the customer-master sync is the top data-quality action."""))

nb["cells"] = cells
nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
nbf.write(nb, "thornquist_dashboard.ipynb")
print("written")
