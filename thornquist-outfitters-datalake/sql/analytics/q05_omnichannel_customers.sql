-- Q5. Customer-segment insight: are omnichannel customers (bought in store AND online) worth more?
--     Joins the customer master (dim_customer) so customers with no purchases are counted too.
WITH per_customer AS (
  SELECT cust_num,
         SUM(CASE WHEN channel = 'store' THEN CAST(line_revenue AS DOUBLE) ELSE 0 END)  AS store_rev,
         SUM(CASE WHEN channel <> 'store' THEN CAST(line_revenue AS DOUBLE) ELSE 0 END) AS online_rev,
         COUNT(DISTINCT order_id) AS orders
  FROM thornquist_curated.fact_sales
  WHERE cust_num IS NOT NULL AND NOT is_orphan_customer
    AND sale_date BETWEEN '2026-08-24' AND '2026-08-30'
  GROUP BY cust_num
),
labelled AS (
  SELECT d.cust_num, d.loyalty_tier,
         CASE WHEN p.cust_num IS NULL                       THEN '4 - No purchase this week'
              WHEN p.store_rev > 0 AND p.online_rev > 0     THEN '1 - Omnichannel'
              WHEN p.store_rev > 0                          THEN '2 - Store only'
              ELSE                                               '3 - Online only' END AS channel_mix,
         COALESCE(p.store_rev + p.online_rev, 0) AS revenue,
         COALESCE(p.orders, 0) AS orders
  FROM thornquist_curated.dim_customer d
  LEFT JOIN per_customer p ON p.cust_num = d.cust_num
)
SELECT channel_mix,
       COUNT(*)                                                       AS customers,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)             AS pct_of_customers,
       SUM(CASE WHEN loyalty_tier = 'Gold' THEN 1 ELSE 0 END)         AS gold_customers,
       ROUND(SUM(revenue), 2)                                         AS revenue,
       ROUND(SUM(revenue) / COUNT(*), 2)                              AS revenue_per_customer,
       ROUND(CAST(SUM(orders) AS DOUBLE) / COUNT(*), 2)               AS orders_per_customer
FROM labelled
GROUP BY channel_mix
ORDER BY channel_mix;
