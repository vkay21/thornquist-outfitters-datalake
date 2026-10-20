#!/usr/bin/env bash
# =============================================================================
# Thornquist - deploy Voke's half (DQ gate, curated layer, Athena tables, monitoring)
# ON TOP OF Aish's existing resources. Run from AWS CloudShell (us-east-1), repo root:
#
#     bash deploy/deploy.sh                          # creates/updates AWS resources and Athena DDL; does not start workflow
#     POS_MODE=gate bash deploy/deploy.sh            # use the DQ-gated POS job instead of Aish's
#     APPLY_GOVERNANCE=1 bash deploy/deploy.sh       # also apply bucket policy + lifecycle (REPLACES existing ones)
#     RUN_WORKFLOW=1 bash deploy/deploy.sh           # also start one pipeline run
#
# Aish's resources are reused, never recreated:
#   bucket thornquist-outfitters-datalake-672869298071 · Glue DB thornquist_retail (raw tables)
#   crawlers thornquist-{pos,customer,ecommerce}-crawler · Lambda thornquist-ecommerce-ingestion
#   jobs thornquist-customer-landing-to-raw, thornquist-pos-raw-to-trusted (-> trusted/pos_final/)
# WARNING: this script changes AWS resources and runs Athena DDL even when RUN_WORKFLOW=0. Review before running.
# =============================================================================
set -euo pipefail
BUCKET=${BUCKET:-thornquist-outfitters-datalake-672869298071}
REGION=${AWS_REGION:-us-east-1}
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ROLE_ARN=${ROLE_ARN:-arn:aws:iam::${ACCOUNT_ID}:role/LabRole}
GLUE_VERSION=${GLUE_VERSION:-4.0}
POS_MODE=${POS_MODE:-aish}            # aish = Aish's thornquist-pos-raw-to-trusted · gate = thornquist-pos-dq-gate
APPLY_GOVERNANCE=${APPLY_GOVERNANCE:-0}
RUN_WORKFLOW=${RUN_WORKFLOW:-0}
ALERT_EMAIL=${ALERT_EMAIL:-}
WG=thornquist-wg
WF=thornquist-pipeline
S3="s3://${BUCKET}"

# ---- Paths aligned to the objects and job output already verified in S3 ----
# The current files are at raw/ root; do not assume raw/{pos,ecommerce,customer}/ folders.
RAW_POS=${RAW_POS:-${S3}/raw/pos_sales_2026-08-24_to_2026-08-30.csv}
RAW_ECOM=${RAW_ECOM:-${S3}/raw/ecommerce_orders.json}
RAW_CUSTOMER=${RAW_CUSTOMER:-${S3}/raw/customer_extract.csv}
JSON_FORMAT=${JSON_FORMAT:-array}     # source JSON is a top-level array
# Existing Aish POS job writes trusted/pos_final/. The optional DQ-gated POS job writes trusted/pos/.
T_POS_GATE=${T_POS_GATE:-${S3}/trusted/pos/}
T_POS_AISH=${T_POS_AISH:-${S3}/trusted/pos_final/}
T_ECOM=${T_ECOM:-${S3}/trusted/ecommerce/}
T_CUSTOMER=${T_CUSTOMER:-${S3}/trusted/customer/}
AISH_POS_JOB=thornquist-pos-raw-to-trusted
if [[ "$POS_MODE" == "gate" ]]; then
  CURATED_POS_PATH="$T_POS_GATE"
else
  CURATED_POS_PATH="$T_POS_AISH"
fi
cd "$(dirname "$0")/.."
echo "Bucket ${BUCKET} · POS_MODE=${POS_MODE} · governance=${APPLY_GOVERNANCE} · run=${RUN_WORKFLOW}"

echo "== 1. Upload job scripts =="
aws s3 cp glue_jobs/ "${S3}/scripts/glue_jobs/" --recursive --exclude "*" --include "*.py" --quiet
LIB="${S3}/scripts/glue_jobs/lib/tq_common.py,${S3}/scripts/glue_jobs/lib/tq_dq.py"

echo "== 2. S3 prefixes (+ governance only if APPLY_GOVERNANCE=1) =="
for z in dq_reports athena-results scripts tmp; do aws s3api put-object --bucket "$BUCKET" --key "${z}/" >/dev/null; done
if [[ "$APPLY_GOVERNANCE" == "1" ]]; then
  aws s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"},"BucketKeyEnabled":true}]}'
  aws s3api put-bucket-lifecycle-configuration --bucket "$BUCKET" --lifecycle-configuration file://governance/s3/lifecycle-policy.json
  sed -e "s/\${BUCKET}/${BUCKET}/g" -e "s/\${ACCOUNT_ID}/${ACCOUNT_ID}/g" governance/s3/bucket-policy-learner-lab.json > /tmp/tq-bucket-policy.json
  aws s3api put-bucket-policy --bucket "$BUCKET" --policy file:///tmp/tq-bucket-policy.json
  echo "   bucket policy, lifecycle and default encryption applied"
else
  echo "   skipped bucket policy/lifecycle (set APPLY_GOVERNANCE=1 once both agree - it replaces existing ones)"
fi

upsert_job () {  # name script default-args-json
  local name=$1 script=$2 args=$3
  local cmd="{\"Name\":\"glueetl\",\"ScriptLocation\":\"${S3}/scripts/glue_jobs/${script}\",\"PythonVersion\":\"3\"}"
  if aws glue get-job --job-name "$name" >/dev/null 2>&1; then
    aws glue update-job --job-name "$name" --job-update "$(python3 - "$ROLE_ARN" "$cmd" "$args" "$GLUE_VERSION" <<'PY'
import json, sys
role, cmd, args, ver = sys.argv[1:]
print(json.dumps({"Role": role, "Command": json.loads(cmd), "DefaultArguments": json.loads(args), "GlueVersion": ver,
                  "WorkerType": "G.1X", "NumberOfWorkers": 2, "Timeout": 10, "MaxRetries": 0}))
PY
)" >/dev/null
  else
    aws glue create-job --name "$name" --role "$ROLE_ARN" --command "$cmd" --default-arguments "$args" \
      --glue-version "$GLUE_VERSION" --worker-type G.1X --number-of-workers 2 --timeout 10 --max-retries 0 >/dev/null
  fi
  echo "   job ${name} ready"
}
base="\"--extra-py-files\":\"${LIB}\",\"--enable-metrics\":\"true\",\"--enable-continuous-cloudwatch-log\":\"true\",\"--TempDir\":\"${S3}/tmp/\""

echo "== 3. Glue jobs =="
upsert_job thornquist-customer-raw-to-trusted raw_to_trusted_customer.py "{${base},
  \"--raw_path\":\"${RAW_CUSTOMER}\",\"--trusted_path\":\"${T_CUSTOMER}\",
  \"--quarantine_path\":\"${S3}/quarantine/customer/\",\"--report_path\":\"${S3}/dq_reports/customer/\"}"
upsert_job thornquist-ecommerce-raw-to-trusted raw_to_trusted_ecommerce.py "{${base},
  \"--raw_path\":\"${RAW_ECOM}\",\"--trusted_customers_path\":\"${T_CUSTOMER}\",\"--json_format\":\"${JSON_FORMAT}\",
  \"--trusted_path\":\"${T_ECOM}\",\"--quarantine_path\":\"${S3}/quarantine/ecommerce/\",
  \"--report_path\":\"${S3}/dq_reports/ecommerce/\"}"
if [[ "$POS_MODE" == "gate" ]]; then
  POS_JOB=thornquist-pos-dq-gate
  upsert_job "$POS_JOB" raw_to_trusted_pos.py "{${base},
    \"--raw_path\":\"${RAW_POS}\",\"--trusted_customers_path\":\"${T_CUSTOMER}\",
    \"--trusted_path\":\"${T_POS_GATE}\",\"--quarantine_path\":\"${S3}/quarantine/pos/\",
    \"--report_path\":\"${S3}/dq_reports/pos/\"}"
else
  POS_JOB=$AISH_POS_JOB
  aws glue get-job --job-name "$POS_JOB" >/dev/null || { echo "Aish's job $POS_JOB not found"; exit 1; }
  echo "   using Aish's ${POS_JOB} (output ${T_POS_AISH}); curated job conforms its schema"
fi
upsert_job thornquist-trusted-to-curated trusted_to_curated.py "{${base},
  \"--pos_path\":\"${CURATED_POS_PATH}\",\"--ecommerce_path\":\"${T_ECOM}\",\"--customers_path\":\"${T_CUSTOMER}\",
  \"--curated_path\":\"${S3}/curated/\"}"

echo "== 4. Glue workflow ${WF}: customer -> (POS || e-commerce) -> curated =="
aws glue create-workflow --name "$WF" --description "Thornquist raw->trusted->curated" >/dev/null 2>&1 || true
mk_trigger () { aws glue create-trigger "$@" >/dev/null 2>&1 || true; }
# Aish's landing->raw customer job and crawlers stay on their own (deactivated) schedules.
mk_trigger --name thornquist-wf-start --workflow-name "$WF" --type ON_DEMAND \
  --actions JobName=thornquist-customer-raw-to-trusted
mk_trigger --name thornquist-wf-weekly --workflow-name "$WF" --type SCHEDULED --schedule "cron(0 6 ? * MON *)" \
  --actions JobName=thornquist-customer-raw-to-trusted     # created, NOT activated (lab budget)
mk_trigger --name thornquist-wf-after-customer --workflow-name "$WF" --type CONDITIONAL --start-on-creation \
  --predicate '{"Conditions":[{"LogicalOperator":"EQUALS","JobName":"thornquist-customer-raw-to-trusted","State":"SUCCEEDED"}]}' \
  --actions "[{\"JobName\":\"${POS_JOB}\"},{\"JobName\":\"thornquist-ecommerce-raw-to-trusted\"}]"
mk_trigger --name thornquist-wf-after-sales --workflow-name "$WF" --type CONDITIONAL --start-on-creation \
  --predicate "{\"Logical\":\"AND\",\"Conditions\":[{\"LogicalOperator\":\"EQUALS\",\"JobName\":\"${POS_JOB}\",\"State\":\"SUCCEEDED\"},{\"LogicalOperator\":\"EQUALS\",\"JobName\":\"thornquist-ecommerce-raw-to-trusted\",\"State\":\"SUCCEEDED\"}]}" \
  --actions JobName=thornquist-trusted-to-curated
echo "   (switching POS_MODE later: delete trigger thornquist-wf-after-customer/-after-sales first, then re-run)"

echo "== 5. Monitoring: SNS topic, EventBridge rule on job FAILURE, quarantine-spike alarms =="
TOPIC_ARN=$(aws sns create-topic --name thornquist-pipeline-alerts --query TopicArn --output text)
[[ -n "$ALERT_EMAIL" ]] && aws sns subscribe --topic-arn "$TOPIC_ARN" --protocol email --notification-endpoint "$ALERT_EMAIL" >/dev/null
aws events put-rule --name thornquist-glue-job-failed --event-pattern \
  '{"source":["aws.glue"],"detail-type":["Glue Job State Change"],"detail":{"jobName":[{"prefix":"thornquist-"}],"state":["FAILED","TIMEOUT","ERROR"]}}' >/dev/null
aws sns set-topic-attributes --topic-arn "$TOPIC_ARN" --attribute-name Policy --attribute-value \
  "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Principal\":{\"Service\":\"events.amazonaws.com\"},\"Action\":\"sns:Publish\",\"Resource\":\"${TOPIC_ARN}\"}]}"
aws events put-targets --rule thornquist-glue-job-failed --targets "Id=sns,Arn=${TOPIC_ARN}" >/dev/null
for src in pos ecommerce; do
  aws cloudwatch put-metric-alarm --alarm-name "thornquist-quarantine-spike-${src}" \
    --namespace Thornquist/DataQuality --metric-name rows_quarantined --dimensions Name=Source,Value=${src} \
    --statistic Sum --period 3600 --evaluation-periods 1 --threshold 25 --comparison-operator GreaterThanThreshold \
    --treat-missing-data notBreaching --alarm-actions "$TOPIC_ARN"
done

echo "== 6. Athena workgroup + tables (thornquist_retail stays Aish's raw DB) =="
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
  RUN_ID=$(aws glue start-workflow-run --name "$WF" --query RunId --output text)
  echo "   workflow run ${RUN_ID} started - Glue console > Workflows > ${WF} > History (~5-8 min)"
  echo "   then: bash deploy/run_queries.sh"
else
  echo "Workflow was NOT started. AWS resources and Athena DDL were still created/updated. To start later: aws glue start-workflow-run --name ${WF}"
fi
echo "Deploy complete."
