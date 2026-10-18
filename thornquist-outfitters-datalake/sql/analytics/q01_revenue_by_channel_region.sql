-- Q1. Which regions drive revenue, and how does each region split between store and online?
SELECT
  region,
  ROUND(SUM(CASE WHEN channel = 'store' THEN CAST(line_revenue AS DOUBLE) ELSE 0 END), 2)  AS store_revenue,
  ROUND(SUM(CASE WHEN channel <> 'store' THEN CAST(line_revenue AS DOUBLE) ELSE 0 END), 2) AS online_revenue,
  ROUND(SUM(CAST(line_revenue AS DOUBLE)), 2)                                              AS total_revenue,
  ROUND(100.0 * SUM(CASE WHEN channel <> 'store' THEN CAST(line_revenue AS DOUBLE) ELSE 0 END)
        / SUM(CAST(line_revenue AS DOUBLE)), 1)                                            AS online_share_pct,
  ROUND(100.0 * SUM(CAST(line_revenue AS DOUBLE))
        / SUM(SUM(CAST(line_revenue AS DOUBLE))) OVER (), 1)                               AS share_of_company_pct
FROM thornquist_curated.fact_sales
WHERE sale_date BETWEEN '2026-08-24' AND '2026-08-30'
GROUP BY region
ORDER BY total_revenue DESC;
