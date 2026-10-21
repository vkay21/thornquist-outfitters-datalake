CREATE EXTERNAL TABLE IF NOT EXISTS thornquist_curated.dim_customer (
  cust_num      string,
  first_name    string   COMMENT 'PII - excluded for analyst by Lake Formation column filter',
  last_name     string   COMMENT 'PII - excluded for analyst',
  email         string   COMMENT 'PII - excluded for analyst',
  signup_date   date,
  signup_year   int,
  loyalty_tier  string,
  home_region   string,
  `_loaded_at`    timestamp
)
STORED AS PARQUET
LOCATION 's3://${BUCKET}/curated/dim_customer/';

CREATE EXTERNAL TABLE IF NOT EXISTS thornquist_curated.agg_daily_sales (
  sale_date    date,
  channel      string,
  region       string,
  category     string,
  orders       bigint,
  sales_lines  bigint,
  units        bigint,
  revenue      decimal(14,2)
)
STORED AS PARQUET
LOCATION 's3://${BUCKET}/curated/agg_daily_sales/';
