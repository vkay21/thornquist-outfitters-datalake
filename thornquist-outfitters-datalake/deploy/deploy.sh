#!/usr/bin/env bash
# =============================================================================
# Thornquist - deploy the DQ gate, curated layer, Athena tables and monitoring
# into a FRESH Learner Lab session. Run from AWS CloudShell (us-east-1) at repo root:
#
#     export BUCKET=<lake bucket name from Aish's setup>
#     bash deploy/deploy.sh                 # deploy + run the workflow once
#     SKIP_POS=1 bash deploy/deploy.sh      # if Aish's POS raw->trusted job is used instead
#
# Prerequisites (Aish's part): bucket with landing/ raw/ zones and the three source
# files already promoted to raw/pos/, raw/ecommerce/, raw/customer/.
# Everything here is idempotent: safe to re-run in the same session.
# =============================================================================
set -euo pipefail
: "${BUCKET:?Set BUCKET first: export BUCKET=<your-lake-bucket>}"
REGION=${AWS_REGION:-us-east-1}
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ROLE_ARN=${ROLE_ARN:-arn:aws:iam::${ACCOUNT_ID}:role/LabRole}
GLUE_VERSION=${GLUE_VERSION:-4.0}
WG=thornquist-wg
ALERT_EMAIL=${ALERT_EMAIL:-}
RUN_WORKFLOW=${RUN_WORKFLOW:-1}
S3="s3://${BUCKET}"
cd "$(dirname "$0")/.."

echo "== 1. Upload job scripts =="
aws s3 cp glue_jobs/ "${S3}/scripts/glue_jobs/" --recursive --exclude "*" --include "*.py" --quiet
LIB="${S3}/scripts/glue_jobs/lib/tq_common.py,${S3}/scripts/glue_jobs/lib/tq_dq.py"

echo "== 2. S3 zones: placeholders, encryption, lifecycle, bucket policy =="
for z in landing raw trusted quarantine dq_reports curated athena-results scripts tmp; do
  aws s3api put-object --bucket "$BUCKET" --key "${z}/" >/dev/null
done
aws s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"},"BucketKeyEnabled":true}]}'
aws s3api put-bucket-lifecycle-configuration --bucket "$BUCKET" --lifecycle-configuration file://governance/s3/lifecycle-policy.json
sed -e "s/\${BUCKET}/${BUCKET}/g" -e "s/\${ACCOUNT_ID}/${ACCOUNT_ID}/g" governance/s3/bucket-policy-learner-lab.json > /tmp/tq-bucket-policy.json
aws s3api put-bucket-policy --bucket "$BUCKET" --policy file:///tmp/tq-bucket-policy.json \
  || echo "   (bucket policy not applied - check for an existing policy from Aish's setup and merge)"

upsert_job () {  # name script default-args-json
  local name=$1 script=$2 args=$3
  local cmd="{\"Name\":\"glueetl\",\"ScriptLocation\":\"${S3}/scripts/glue_jobs/${script}\",\"PythonVersion\":\"3\"}"
  local common=(--role "$ROLE_ARN" --command "$cmd" --default-arguments "$args" --glue-version "$GLUE_VERSION"
                --worker-type G.1X --number-of-workers 2 --timeout 10 --max-retries 0)
  if aws glue get-job --job-name "$name" >/dev/null 2>&1; then
    aws glue update-job --job-name "$name" --job-update "$(python3 - "$ROLE_ARN" "$cmd" "$args" "$GLUE_VERSION" <<'PY'
import json, sys
role, cmd, args, ver = sys.argv[1:]
print(json.dumps({"Role": role, "Command": json.loads(cmd), "DefaultArguments": json.loads(args), "GlueVersion": ver,
                  "WorkerType": "G.1X", "NumberOfWorkers": 2, "Timeout": 10, "MaxRetries": 0}))
PY
)" >/dev/null
  else
    aws glue create-job --name "$name" "${common[@]}" >/dev/null
  fi
  echo "   job ${name} ready"
}
base="\"--extra-py-files\":\"${LIB}\",\"--enable-metrics\":\"true\",\"--enable-continuous-cloudwatch-log\":\"true\",\"--TempDir\":\"${S3}/tmp/\""

echo "== 3. Glue jobs =="
upsert_job tq-raw-to-trusted-customer raw_to_trusted_customer.py "{${base},
  \"--raw_path\":\"${S3}/raw/customer/\",\"--trusted_path\":\"${S3}/trusted/customers/\",
  \"--quarantine_path\":\"${S3}/quarantine/customer/\",\"--report_path\":\"${S3}/dq_reports/customer/\"}"
if [[ -z "${SKIP_POS:-}" ]]; then
upsert_job tq-raw-to-trusted-pos raw_to_trusted_pos.py "{${base},
  \"--raw_path\":\"${S3}/raw/pos/\",\"--trusted_customers_path\":\"${S3}/trusted/customers/\",
  \"--trusted_path\":\"${S3}/trusted/pos_sales/\",\"--quarantine_path\":\"${S3}/quarantine/pos/\",
  \"--report_path\":\"${S3}/dq_reports/pos/\"}"
fi
upsert_job tq-raw-to-trusted-ecommerce raw_to_trusted_ecommerce.py "{${base},
  \"--raw_path\":\"${S3}/raw/ecommerce/\",\"--trusted_customers_path\":\"${S3}/trusted/customers/\",
  \"--trusted_path\":\"${S3}/trusted/ecommerce_order_lines/\",\"--quarantine_path\":\"${S3}/quarantine/ecommerce/\",
  \"--report_path\":\"${S3}/dq_reports/ecommerce/\"}"
upsert_job tq-trusted-to-curated trusted_to_curated.py "{${base},
  \"--trusted_path\":\"${S3}/trusted/\",\"--curated_path\":\"${S3}/curated/\"}"

echo "== 4. Glue workflow: customer -> (pos, ecommerce) -> curated, weekly schedule =="
aws glue create-workflow --name tq-pipeline --description "Thornquist raw->trusted->curated" >/dev/null 2>&1 || true
mk_trigger () { aws glue create-trigger "$@" >/dev/null 2>&1 || true; }
mk_trigger --name tq-start --workflow-name tq-pipeline --type ON_DEMAND \
  --actions JobName=tq-raw-to-trusted-customer
mk_trigger --name tq-weekly --workflow-name tq-pipeline --type SCHEDULED --schedule "cron(0 6 ? * MON *)" \
  --actions JobName=tq-raw-to-trusted-customer   # created but NOT activated (Learner Lab budget)
if [[ -z "${SKIP_POS:-}" ]]; then
  SALES_ACTIONS='[{"JobName":"tq-raw-to-trusted-pos"},{"JobName":"tq-raw-to-trusted-ecommerce"}]'
  CURATED_COND='{"Logical":"AND","Conditions":[{"LogicalOperator":"EQUALS","JobName":"tq-raw-to-trusted-pos","State":"SUCCEEDED"},{"LogicalOperator":"EQUALS","JobName":"tq-raw-to-trusted-ecommerce","State":"SUCCEEDED"}]}'
else
  SALES_ACTIONS='[{"JobName":"tq-raw-to-trusted-ecommerce"}]'
  CURATED_COND='{"Logical":"AND","Conditions":[{"LogicalOperator":"EQUALS","JobName":"tq-raw-to-trusted-ecommerce","State":"SUCCEEDED"}]}'
fi
mk_trigger --name tq-after-customer --workflow-name tq-pipeline --type CONDITIONAL --start-on-creation \
  --predicate '{"Conditions":[{"LogicalOperator":"EQUALS","JobName":"tq-raw-to-trusted-customer","State":"SUCCEEDED"}]}' \
  --actions "$SALES_ACTIONS"
mk_trigger --name tq-after-sales --workflow-name tq-pipeline --type CONDITIONAL --start-on-creation \
  --predicate "$CURATED_COND" --actions JobName=tq-trusted-to-curated

echo "== 5. Monitoring: SNS topic, EventBridge rule on job FAILURE, quarantine-spike alarm =="
TOPIC_ARN=$(aws sns create-topic --name tq-pipeline-alerts --query TopicArn --output text)
[[ -n "$ALERT_EMAIL" ]] && aws sns subscribe --topic-arn "$TOPIC_ARN" --protocol email --notification-endpoint "$ALERT_EMAIL" >/dev/null
aws events put-rule --name tq-glue-job-failed --event-pattern \
  '{"source":["aws.glue"],"detail-type":["Glue Job State Change"],"detail":{"jobName":[{"prefix":"tq-"}],"state":["FAILED","TIMEOUT","ERROR"]}}' >/dev/null
aws sns set-topic-attributes --topic-arn "$TOPIC_ARN" --attribute-name Policy --attribute-value \
  "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Principal\":{\"Service\":\"events.amazonaws.com\"},\"Action\":\"sns:Publish\",\"Resource\":\"${TOPIC_ARN}\"}]}"
aws events put-targets --rule tq-glue-job-failed --targets "Id=sns,Arn=${TOPIC_ARN}" >/dev/null
for src in pos ecommerce; do
  aws cloudwatch put-metric-alarm --alarm-name "tq-quarantine-spike-${src}" \
    --namespace Thornquist/DataQuality --metric-name rows_quarantined --dimensions Name=Source,Value=${src} \
    --statistic Sum --period 3600 --evaluation-periods 1 --threshold 25 --comparison-operator GreaterThanThreshold \
    --treat-missing-data notBreaching --alarm-actions "$TOPIC_ARN"
done

echo "== 6. Athena workgroup + tables =="
aws athena create-work-group --name "$WG" --configuration \
  "ResultConfiguration={OutputLocation=${S3}/athena-results/},EnforceWorkGroupConfiguration=true,PublishCloudWatchMetricsEnabled=true,BytesScannedCutoffPerQuery=1073741824" \
  >/dev/null 2>&1 || true
run_athena () {
  local qid state
  qid=$(aws athena start-query-execution --work-group "$WG" --query-string "$1" --query QueryExecutionId --output text)
  while true; do
    state=$(aws athena get-query-execution --query-execution-id "$qid" --query QueryExecution.Status.State --output text)
    [[ "$state" == "SUCCEEDED" || "$state" == "FAILED" || "$state" == "CANCELLED" ]] && break; sleep 1
  done
  [[ "$state" == "SUCCEEDED" ]] || aws athena get-query-execution --query-execution-id "$qid" \
    --query QueryExecution.Status.StateChangeReason --output text
  echo "   ${state}: ${1:0:70}" | tr '\n' ' '; echo
}
for f in sql/ddl/*.sql; do
  python3 - "$f" "$BUCKET" > /tmp/tq-stmts.txt <<'PY'
import sys
sql = open(sys.argv[1]).read().replace("${BUCKET}", sys.argv[2])
body = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
for s in body.split(";"):
    if s.strip():
        print(s.strip().replace("\n", " "), end="\x1e")
PY
  while IFS= read -r -d $'\x1e' stmt; do
    [[ -n "$stmt" ]] && run_athena "$stmt"
  done < /tmp/tq-stmts.txt
done

if [[ "$RUN_WORKFLOW" == "1" ]]; then
  echo "== 7. Run the pipeline once =="
  RUN_ID=$(aws glue start-workflow-run --name tq-pipeline --query RunId --output text)
  echo "   workflow run ${RUN_ID} started - watch: Glue console > Workflows > tq-pipeline > History"
  echo "   (takes ~5-8 min; Glue cold-start dominates). Then run: bash deploy/run_queries.sh"
fi
echo "Deploy complete."
