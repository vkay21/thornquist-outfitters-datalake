-- Q6. Inventory allocation: top 3 products by units demanded in each region (all channels),
--     with the share of that demand coming from online orders that ship INTO the region.
WITH demand AS (
  SELECT region, product_name, category,
         SUM(quantity) AS units,
         SUM(CASE WHEN channel <> 'store' THEN quantity ELSE 0 END) AS online_units
  FROM thornquist_curated.fact_sales
  WHERE sale_date BETWEEN '2026-08-24' AND '2026-08-30'
  GROUP BY region, product_name, category
),
ranked AS (
  SELECT *, RANK() OVER (PARTITION BY region ORDER BY units DESC, product_name) AS rnk
  FROM demand
)
SELECT region, rnk AS demand_rank, product_name, category, units, online_units,
       ROUND(100.0 * online_units / units, 1) AS online_share_pct
FROM ranked
WHERE rnk <= 3
ORDER BY region, rnk;
