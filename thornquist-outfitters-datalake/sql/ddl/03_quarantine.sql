-- Quarantine tables: manually defined because the files carry array<string> rule columns
-- and a batch_id= folder partition that the crawler would otherwise guess at.
-- Columns are the raw (string) source columns + DQ metadata.
CREATE EXTERNAL TABLE IF NOT EXISTS thornquist_quarantine.pos (
  transaction_id string, store_id string, store_name string, region string, sale_date string,
  category string, product_name string, quantity string, unit_price string, payment_method string,
  cust_num string, _source_file string,
  dq_remediations array<string>, dq_failed_rules array<string>, dq_flags array<string>,
  dq_status string, dq_batch_id string
)
PARTITIONED BY (batch_id string)
STORED AS PARQUET
LOCATION 's3://${BUCKET}/quarantine/pos/'
TBLPROPERTIES ('projection.enabled'='true', 'projection.batch_id.type'='injected');

CREATE EXTERNAL TABLE IF NOT EXISTS thornquist_quarantine.ecommerce (
  order_id bigint, order_timestamp string, cust_ref bigint, channel string, shipping_region string,
  order_total double, extra_attributes string, _source_file string,
  dq_remediations array<string>, dq_failed_rules array<string>, dq_flags array<string>,
  dq_status string, dq_batch_id string
)
PARTITIONED BY (batch_id string)
STORED AS PARQUET
LOCATION 's3://${BUCKET}/quarantine/ecommerce/'
TBLPROPERTIES ('projection.enabled'='true', 'projection.batch_id.type'='injected');
-- 'injected' projection: queries must filter WHERE batch_id = '...'. To browse all batches,
-- run a crawler on quarantine/ instead, or: MSCK REPAIR TABLE after disabling projection.
