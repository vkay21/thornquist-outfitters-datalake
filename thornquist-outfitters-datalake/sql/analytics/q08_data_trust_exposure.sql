-- Q8. Data trust: how much revenue sits on flagged records (orphaned customers) per channel?
--     Tells leadership how much of the customer-level analysis rests on unmatched IDs.
SELECT
  channel,
  COUNT(DISTINCT order_id)                                                            AS orders,
  COUNT(DISTINCT CASE WHEN is_orphan_customer THEN order_id END)                      AS orphan_orders,
  COUNT(DISTINCT CASE WHEN is_orphan_customer THEN cust_num END)                      AS orphan_customer_ids,
  ROUND(SUM(CASE WHEN is_orphan_customer THEN CAST(line_revenue AS DOUBLE) ELSE 0 END), 2) AS orphan_revenue,
  ROUND(100.0 * SUM(CASE WHEN is_orphan_customer THEN CAST(line_revenue AS DOUBLE) ELSE 0 END)
        / SUM(CAST(line_revenue AS DOUBLE)), 1)                                       AS orphan_revenue_pct,
  ROUND(100.0 * SUM(CASE WHEN is_walk_in THEN CAST(line_revenue AS DOUBLE) ELSE 0 END)
        / SUM(CAST(line_revenue AS DOUBLE)), 1)                                       AS walk_in_revenue_pct
FROM thornquist_curated.fact_sales
GROUP BY channel
ORDER BY channel;
