-- Q4. How do online and in-store behaviour differ by customer segment (loyalty tier)?
--     Blends the legacy customer extract (loyalty_tier) with sales from both channels.
SELECT
  customer_segment,
  channel,
  COUNT(DISTINCT cust_num)                                                   AS customers,
  COUNT(DISTINCT order_id)                                                   AS orders,
  ROUND(SUM(CAST(line_revenue AS DOUBLE)), 2)                                AS revenue,
  ROUND(SUM(CAST(line_revenue AS DOUBLE)) / COUNT(DISTINCT order_id), 2)     AS avg_order_value,
  ROUND(CAST(SUM(quantity) AS DOUBLE) / COUNT(DISTINCT order_id), 2)         AS units_per_order,
  ROUND(SUM(CAST(line_revenue AS DOUBLE)) / NULLIF(COUNT(DISTINCT cust_num), 0), 2) AS revenue_per_customer
FROM thornquist_curated.fact_sales
WHERE sale_date BETWEEN '2026-08-24' AND '2026-08-30'
GROUP BY customer_segment, channel
ORDER BY CASE customer_segment WHEN 'Gold' THEN 1 WHEN 'Silver' THEN 2 WHEN 'Standard' THEN 3
                               WHEN 'Unmatched' THEN 4 ELSE 5 END, channel;
