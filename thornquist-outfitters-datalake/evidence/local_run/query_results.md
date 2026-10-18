# Local run - Athena query results (executed with DuckDB on the curated Parquet)


## q01_revenue_by_channel_region

_Q1. Which regions drive revenue, and how does each region split between store and online?_

| region           |   store_revenue |   online_revenue |   total_revenue |   online_share_pct |   share_of_company_pct |
|:-----------------|----------------:|-----------------:|----------------:|-------------------:|-----------------------:|
| Ontario          |         58817.1 |          22858.1 |         81675.2 |               28   |                   24.5 |
| Quebec           |         46653.4 |          28628.8 |         75282.2 |               38   |                   22.6 |
| Alberta          |         45447.9 |          21034.3 |         66482.2 |               31.6 |                   19.9 |
| British Columbia |         42863.2 |          21673.7 |         64536.9 |               33.6 |                   19.4 |
| Atlantic         |         20780.2 |          24655   |         45435.2 |               54.3 |                   13.6 |


## q02_category_by_channel

_Q2. Which product categories sell best in each channel (revenue, units, average selling price)?_

| category    | channel   |   units |   revenue |   avg_selling_price |   pct_of_channel_revenue |
|:------------|:----------|--------:|----------:|--------------------:|-------------------------:|
| Apparel     | online    |     185 |   31501.9 |              170.28 |                     26.5 |
| Footwear    | online    |     175 |   30499.2 |              174.28 |                     25.7 |
| Camping     | online    |     172 |   29653.2 |              172.4  |                     25   |
| Accessories | online    |     166 |   27195.6 |              163.83 |                     22.9 |
| Camping     | store     |     337 |   56840.1 |              168.66 |                     26.5 |
| Accessories | store     |     325 |   54127.7 |              166.55 |                     25.2 |
| Apparel     | store     |     305 |   54094.6 |              177.36 |                     25.2 |
| Footwear    | store     |     284 |   49499.5 |              174.29 |                     23.1 |


## q03_daily_trend_growth

_Q3. Daily revenue trend per channel with day-over-day growth (is growth coming from stores or online?)_

| sale_date   | channel   |   orders |   revenue |   dod_growth_pct |
|:------------|:----------|---------:|----------:|-----------------:|
| 2026-08-24  | online    |       40 |   18343.3 |            nan   |
| 2026-08-25  | online    |       29 |   13105.1 |            -28.6 |
| 2026-08-26  | online    |       31 |   16736.9 |             27.7 |
| 2026-08-27  | online    |       36 |   18771.8 |             12.2 |
| 2026-08-28  | online    |       38 |   15443   |            -17.7 |
| 2026-08-29  | online    |       42 |   19471.8 |             26.1 |
| 2026-08-30  | online    |       38 |   16978.1 |            -12.8 |
| 2026-08-24  | store     |      140 |   30040.9 |            nan   |
| 2026-08-25  | store     |      159 |   29339.4 |             -2.3 |
| 2026-08-26  | store     |      134 |   29893.7 |              1.9 |
| 2026-08-27  | store     |      170 |   32322.6 |              8.1 |
| 2026-08-28  | store     |      163 |   35912.8 |             11.1 |
| 2026-08-29  | store     |      146 |   27461.8 |            -23.5 |
| 2026-08-30  | store     |      136 |   29590.6 |              7.8 |


## q04_segment_channel_behaviour

_Q4. How do online and in-store behaviour differ by customer segment (loyalty tier)?_

| customer_segment   | channel   |   customers |   orders |   revenue |   avg_order_value |   units_per_order |   revenue_per_customer |
|:-------------------|:----------|------------:|---------:|----------:|------------------:|------------------:|-----------------------:|
| Gold               | online    |          11 |       17 |   5906.61 |            347.45 |              2.12 |                 536.96 |
| Gold               | store     |          35 |       82 |  17548.4  |            214    |              1.18 |                 501.38 |
| Silver             | online    |          37 |       50 |  25928.5  |            518.57 |              3.2  |                 700.77 |
| Silver             | store     |          71 |      183 |  34693.6  |            189.58 |              1.16 |                 488.64 |
| Standard           | online    |         124 |      154 |  70707.8  |            459.14 |              2.66 |                 570.22 |
| Standard           | store     |         247 |      598 | 126547    |            211.62 |              1.21 |                 512.34 |
| Unmatched          | online    |          28 |       33 |  16307.1  |            494.15 |              2.82 |                 582.4  |
| Walk-in            | store     |           0 |      185 |  35772.9  |            193.37 |              1.19 |                 nan    |


## q05_omnichannel_customers

_Q5. Customer-segment insight: are omnichannel customers (bought in store AND online) worth more?_

| channel_mix               |   customers |   pct_of_customers |   gold_customers |   revenue |   revenue_per_customer |   orders_per_customer |
|:--------------------------|------------:|-------------------:|-----------------:|----------:|-----------------------:|----------------------:|
| 1 - Omnichannel           |         159 |               39.8 |               10 | 177629    |                1117.16 |                  3.77 |
| 2 - Store only            |         194 |               48.5 |               25 |  97442.2  |                 502.28 |                  2.41 |
| 3 - Online only           |          13 |                3.3 |                1 |   6260.87 |                 481.61 |                  1.31 |
| 4 - No purchase this week |          34 |                8.5 |                4 |      0    |                   0    |                  0    |


## q06_demand_vs_allocation

_Q6. Inventory allocation: top 3 products by units demanded in each region (all channels),_

| region           |   demand_rank | product_name          | category    |   units |   online_units |   online_share_pct |
|:-----------------|--------------:|:----------------------|:------------|--------:|---------------:|-------------------:|
| Alberta          |             1 | Alpine Hiking Shoe    | Footwear    |      34 |             10 |               29.4 |
| Alberta          |             2 | Sleeping Bag -10C     | Camping     |      34 |              6 |               17.6 |
| Alberta          |             3 | Hydration Pack        | Accessories |      29 |              4 |               13.8 |
| Atlantic         |             1 | Insulated Winter Boot | Footwear    |      22 |             16 |               72.7 |
| Atlantic         |             2 | Sleeping Bag -10C     | Camping     |      20 |              9 |               45   |
| Atlantic         |             3 | Trail Runner Low      | Footwear    |      20 |             13 |               65   |
| British Columbia |             1 | 2-Person Tent         | Camping     |      32 |              8 |               25   |
| British Columbia |             2 | Insulated Winter Boot | Footwear    |      25 |              9 |               36   |
| British Columbia |             3 | Merino Base Layer     | Apparel     |      25 |              7 |               28   |
| Ontario          |             1 | Fleece Pullover       | Apparel     |      42 |             14 |               33.3 |
| Ontario          |             2 | 2-Person Tent         | Camping     |      41 |             15 |               36.6 |
| Ontario          |             3 | Trailrunner Boot      | Footwear    |      35 |             11 |               31.4 |
| Quebec           |             1 | Sleeping Pad          | Camping     |      41 |             10 |               24.4 |
| Quebec           |             2 | Wool Socks 3-Pack     | Accessories |      36 |             13 |               36.1 |
| Quebec           |             3 | Alpine Hiking Shoe    | Footwear    |      27 |              6 |               22.2 |


## q07_store_customer_capture

_Q7. Store performance and loyalty capture: revenue per store and the % of transactions_

|   store_id | store_name             | region           |   transactions |   revenue |   avg_ticket |   walk_in_pct |   revenue_rank |
|-----------:|:-----------------------|:-----------------|---------------:|----------:|-------------:|--------------:|---------------:|
|          1 | Toronto Yonge St       | Ontario          |            105 |   23628.5 |       225.03 |          18.1 |              1 |
|          7 | Victoria Douglas       | British Columbia |            118 |   23591.1 |       199.92 |          19.5 |              2 |
|          4 | Montreal Ste-Catherine | Quebec           |            109 |   23431.2 |       214.96 |          15.6 |              3 |
|          5 | Quebec City Laurier    | Quebec           |            119 |   23222.2 |       195.14 |          17.6 |              4 |
|          9 | Edmonton Whyte Ave     | Alberta          |            112 |   22895.1 |       204.42 |          17.9 |              5 |
|          8 | Calgary Stephen Ave    | Alberta          |            109 |   22552.8 |       206.91 |          19.3 |              6 |
|         10 | Halifax Spring Garden  | Atlantic         |            107 |   20780.2 |       194.21 |          18.7 |              7 |
|          6 | Vancouver Robson       | British Columbia |             98 |   19272.1 |       196.65 |          21.4 |              8 |
|          2 | Toronto Scarborough    | Ontario          |             88 |   18227.7 |       207.13 |          13.6 |              9 |
|          3 | Ottawa Rideau          | Ontario          |             83 |   16960.9 |       204.35 |          13.3 |             10 |


## q08_data_trust_exposure

_Q8. Data trust: how much revenue sits on flagged records (orphaned customers) per channel?_

| channel   |   orders |   orphan_orders |   orphan_customer_ids |   orphan_revenue |   orphan_revenue_pct |   walk_in_revenue_pct |
|:----------|---------:|----------------:|----------------------:|-----------------:|---------------------:|----------------------:|
| online    |      260 |              34 |                    28 |          17375.2 |                 14.1 |                   0   |
| store     |     1048 |               0 |                     0 |              0   |                  0   |                  16.7 |
