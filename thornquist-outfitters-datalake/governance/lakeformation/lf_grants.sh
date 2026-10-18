#!/usr/bin/env bash
# Lake Formation permission set for Thornquist (run in CloudShell, us-east-1).
#
# Learner Lab reality: we cannot create the analyst / regional-manager IAM roles, so this
# script takes their ARNs as variables. For the demo, point ANALYST_ARN at any principal you
# are allowed to use (or show the grants in the console as "design, not deployed").
# Grants to principals that don't exist will be rejected - that is expected in the lab.
set -euo pipefail
: "${BUCKET:?export BUCKET=<lake bucket>}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ANALYST_ARN=${ANALYST_ARN:-arn:aws:iam::${ACCOUNT_ID}:role/tq-analyst-role}
REGIONAL_MGR_ARN=${REGIONAL_MGR_ARN:-arn:aws:iam::${ACCOUNT_ID}:role/tq-regional-manager-ontario-role}
STEWARD_ARN=${STEWARD_ARN:-arn:aws:iam::${ACCOUNT_ID}:role/tq-data-steward-role}
ETL_ARN=${ETL_ARN:-arn:aws:iam::${ACCOUNT_ID}:role/LabRole}
ADMIN_ARN=${ADMIN_ARN:-arn:aws:iam::${ACCOUNT_ID}:role/voclabs}

echo "1) Make the console role a Lake Formation admin (needed once per account)"
aws lakeformation put-data-lake-settings --data-lake-settings "{\"DataLakeAdmins\":[{\"DataLakePrincipalIdentifier\":\"${ADMIN_ARN}\"}]}" || true

echo "2) Register the curated location so LF (not raw S3 IAM) governs reads"
aws lakeformation register-resource --resource-arn "arn:aws:s3:::${BUCKET}/curated" --use-service-linked-role 2>/dev/null \
  || aws lakeformation register-resource --resource-arn "arn:aws:s3:::${BUCKET}/curated" --role-arn "${ETL_ARN}" || true

echo "3) Stop IAM-only access to curated: remove the IAMAllowedPrincipals default grant"
aws lakeformation revoke-permissions --principal DataLakePrincipalIdentifier=IAM_ALLOWED_PRINCIPALS \
  --resource '{"Database":{"Name":"thornquist_curated"}}' --permissions ALL || true
aws lakeformation revoke-permissions --principal DataLakePrincipalIdentifier=IAM_ALLOWED_PRINCIPALS \
  --resource '{"Table":{"DatabaseName":"thornquist_curated","TableWildcard":{}}}' --permissions ALL || true

echo "4) ETL role: write curated location + manage curated tables"
aws lakeformation grant-permissions --principal DataLakePrincipalIdentifier=${ETL_ARN} \
  --resource "{\"DataLocation\":{\"ResourceArn\":\"arn:aws:s3:::${BUCKET}/curated\"}}" --permissions DATA_LOCATION_ACCESS || true
aws lakeformation grant-permissions --principal DataLakePrincipalIdentifier=${ETL_ARN} \
  --resource '{"Database":{"Name":"thornquist_curated"}}' --permissions CREATE_TABLE ALTER DESCRIBE || true
aws lakeformation grant-permissions --principal DataLakePrincipalIdentifier=${ETL_ARN} \
  --resource '{"Table":{"DatabaseName":"thornquist_curated","TableWildcard":{}}}' --permissions SELECT INSERT ALTER DESCRIBE || true

echo "4b) Console role keeps SELECT on curated, so Athena queries in the demo still work once IAMAllowedPrincipals is revoked"
aws lakeformation grant-permissions --principal DataLakePrincipalIdentifier=${ADMIN_ARN} \
  --resource '{"Database":{"Name":"thornquist_curated"}}' --permissions ALL || true
aws lakeformation grant-permissions --principal DataLakePrincipalIdentifier=${ADMIN_ARN} \
  --resource '{"Table":{"DatabaseName":"thornquist_curated","TableWildcard":{}}}' --permissions ALL || true

echo "5) ANALYST: curated zone only"
aws lakeformation grant-permissions --principal DataLakePrincipalIdentifier=${ANALYST_ARN} \
  --resource '{"Database":{"Name":"thornquist_curated"}}' --permissions DESCRIBE
for t in fact_sales agg_daily_sales; do
  aws lakeformation grant-permissions --principal DataLakePrincipalIdentifier=${ANALYST_ARN} \
    --resource "{\"Table\":{\"DatabaseName\":\"thornquist_curated\",\"Name\":\"${t}\"}}" --permissions SELECT DESCRIBE
done
echo "   column-level: dim_customer WITHOUT PII columns (stretch goal)"
aws lakeformation grant-permissions --principal DataLakePrincipalIdentifier=${ANALYST_ARN} \
  --resource '{"TableWithColumns":{"DatabaseName":"thornquist_curated","Name":"dim_customer","ColumnWildcard":{"ExcludedColumnNames":["first_name","last_name","email"]}}}' \
  --permissions SELECT

echo "6) REGIONAL MANAGER (Ontario): row-level filter on fact_sales (stretch goal)"
aws lakeformation create-data-cells-filter --table-data "{
  \"TableCatalogId\":\"${ACCOUNT_ID}\",\"DatabaseName\":\"thornquist_curated\",\"TableName\":\"fact_sales\",
  \"Name\":\"ontario_only\",\"RowFilter\":{\"FilterExpression\":\"region = 'Ontario'\"},
  \"ColumnWildcard\":{\"ExcludedColumnNames\":[\"cust_num\"]}}" || true
aws lakeformation grant-permissions --principal DataLakePrincipalIdentifier=${REGIONAL_MGR_ARN} \
  --resource "{\"DataCellsFilter\":{\"TableCatalogId\":\"${ACCOUNT_ID}\",\"DatabaseName\":\"thornquist_curated\",\"TableName\":\"fact_sales\",\"Name\":\"ontario_only\"}}" \
  --permissions SELECT
aws lakeformation grant-permissions --principal DataLakePrincipalIdentifier=${REGIONAL_MGR_ARN} \
  --resource '{"Database":{"Name":"thornquist_curated"}}' --permissions DESCRIBE

echo "7) DATA STEWARD: trusted + quarantine (to review flagged / rejected records)"
for db in thornquist_trusted thornquist_quarantine; do
  aws lakeformation grant-permissions --principal DataLakePrincipalIdentifier=${STEWARD_ARN} \
    --resource "{\"Table\":{\"DatabaseName\":\"${db}\",\"TableWildcard\":{}}}" --permissions SELECT DESCRIBE
done

echo "Done. Verify with: aws lakeformation list-permissions --resource '{\"Database\":{\"Name\":\"thornquist_curated\"}}'"
