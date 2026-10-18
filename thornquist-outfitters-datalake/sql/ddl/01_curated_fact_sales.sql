-- MANUALLY CURATED TABLE DEFINITION (brief requirement: "at least one manually curated
-- table definition where a crawler alone would misinterpret the schema").
--
-- Why not a crawler here?
--   * sale_date / channel would be inferred as generic strings with partitions that only
--     become visible after every re-crawl; we use PARTITION PROJECTION instead, so a new
--     day's partition is queryable the moment the ETL writes it - no crawler, no MSCK REPAIR.
--   * cust_num must stay STRING (a crawler sampling the data can infer BIGINT and drop
--     leading zeros); money must be DECIMAL, not DOUBLE.
CREATE EXTERNAL TABLE IF NOT EXISTS thornquist_curated.fact_sales (
  sales_line_id         string        COMMENT 'POS-<txn>-1 or WEB-<order>-<line>',
  order_id              bigint        COMMENT 'POS transaction_id or e-commerce order_id',
  line_no               int,
  sale_ts_utc           timestamp     COMMENT 'E-commerce only - POS exports carry no time',
  sale_week             date,
  store_id              int           COMMENT 'NULL for e-commerce',
  store_name            string        COMMENT '"E-commerce" for online/app',
  region                string        COMMENT 'Store region (POS) or shipping region (e-com) - conflict C4',
  category              string        COMMENT 'Conformed taxonomy - conflict C3',
  product_name          string,
  sku                   string        COMMENT 'E-commerce only',
  quantity              int,
  unit_price            decimal(10,2),
  line_revenue          decimal(12,2),
  currency              string,
  payment_method        string        COMMENT 'POS only',
  cust_num              string        COMMENT 'Conformed customer key (conflict C2), NULL = walk-in',
  is_walk_in            boolean,
  is_orphan_customer    boolean       COMMENT 'DQ rule POS-08 / ECO-08 flag',
  loyalty_tier          string,
  customer_home_region  string,
  customer_segment      string        COMMENT 'Gold/Silver/Standard/Walk-in/Unmatched',
  dq_flagged            boolean,
  _loaded_at            timestamp
)
PARTITIONED BY (channel string, sale_date string)
STORED AS PARQUET
LOCATION 's3://${BUCKET}/curated/fact_sales/'
TBLPROPERTIES (
  'parquet.compression'          = 'SNAPPY',
  'projection.enabled'           = 'true',
  'projection.channel.type'      = 'enum',
  'projection.channel.values'    = 'store,online,app',
  'projection.sale_date.type'    = 'date',
  'projection.sale_date.format'  = 'yyyy-MM-dd',
  'projection.sale_date.range'   = '2026-01-01,NOW',
  'projection.sale_date.interval'= '1',
  'projection.sale_date.interval.unit' = 'DAYS',
  'storage.location.template'    = 's3://${BUCKET}/curated/fact_sales/channel=${channel}/sale_date=${sale_date}'
);
