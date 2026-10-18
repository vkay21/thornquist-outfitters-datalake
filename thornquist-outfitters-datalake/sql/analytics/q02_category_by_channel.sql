-- Q2. Which product categories sell best in each channel (revenue, units, average selling price)?
SELECT
  category,
  channel,
  SUM(quantity)                                                      AS units,
  ROUND(SUM(CAST(line_revenue AS DOUBLE)), 2)                        AS revenue,
  ROUND(SUM(CAST(line_revenue AS DOUBLE)) / SUM(quantity), 2)        AS avg_selling_price,
  ROUND(100.0 * SUM(CAST(line_revenue AS DOUBLE))
        / SUM(SUM(CAST(line_revenue AS DOUBLE))) OVER (PARTITION BY channel), 1) AS pct_of_channel_revenue
FROM thornquist_curated.fact_sales
WHERE sale_date BETWEEN '2026-08-24' AND '2026-08-30'
GROUP BY category, channel
ORDER BY channel, revenue DESC;
