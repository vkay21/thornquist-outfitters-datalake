-- Q7. Store performance and loyalty capture: revenue per store and the % of transactions
--     where the customer was NOT identified (walk-in placeholder 0000000 in the source).
SELECT
  store_id, store_name, region,
  COUNT(*)                                                                   AS transactions,
  ROUND(SUM(CAST(line_revenue AS DOUBLE)), 2)                                AS revenue,
  ROUND(SUM(CAST(line_revenue AS DOUBLE)) / COUNT(*), 2)                     AS avg_ticket,
  ROUND(100.0 * SUM(CASE WHEN is_walk_in THEN 1 ELSE 0 END) / COUNT(*), 1)   AS walk_in_pct,
  RANK() OVER (ORDER BY SUM(CAST(line_revenue AS DOUBLE)) DESC)              AS revenue_rank
FROM thornquist_curated.fact_sales
WHERE channel = 'store' AND sale_date BETWEEN '2026-08-24' AND '2026-08-30'
GROUP BY store_id, store_name, region
ORDER BY revenue DESC;
