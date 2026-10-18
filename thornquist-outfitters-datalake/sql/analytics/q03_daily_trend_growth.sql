-- Q3. Daily revenue trend per channel with day-over-day growth (is growth coming from stores or online?)
WITH daily AS (
  SELECT sale_date, channel,
         SUM(CAST(line_revenue AS DOUBLE)) AS revenue,
         COUNT(DISTINCT order_id)          AS orders
  FROM thornquist_curated.fact_sales
  WHERE sale_date BETWEEN '2026-08-24' AND '2026-08-30'
  GROUP BY sale_date, channel
)
SELECT
  sale_date,
  channel,
  orders,
  ROUND(revenue, 2) AS revenue,
  ROUND(100.0 * (revenue - LAG(revenue) OVER (PARTITION BY channel ORDER BY sale_date))
        / LAG(revenue) OVER (PARTITION BY channel ORDER BY sale_date), 1) AS dod_growth_pct
FROM daily
ORDER BY channel, sale_date;
