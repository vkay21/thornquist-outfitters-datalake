-- Every Glue run writes one single-line JSON DQ report: dq_reports/<source>/batch_id=<id>/dq_report.json
-- This table turns the reports into a queryable DQ history (pass/fail per rule per batch).
CREATE EXTERNAL TABLE IF NOT EXISTS thornquist_quarantine.dq_reports (
  source               string,
  batch_id             string,
  rows_checked         bigint,
  rows_promoted        bigint,
  rows_promoted_flagged bigint,
  rows_quarantined     bigint,
  reject_pct           double,
  max_reject_pct       double,
  batch_decision       string,
  remediations_applied map<string,bigint>,
  rules array<struct<rule_id:string, name:string, dimension:string, action:string,
                     failed_rows:bigint, status:string, description:string>>
)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
LOCATION 's3://${BUCKET}/dq_reports/';
-- (Files sit in sub-folders; Athena reads them recursively for non-partitioned tables.)

-- Example: rule-level history
-- SELECT r.source, r.batch_id, x.rule_id, x.status, x.failed_rows
-- FROM thornquist_quarantine.dq_reports r CROSS JOIN UNNEST(r.rules) AS t(x)
-- ORDER BY 1, 2, 3;
