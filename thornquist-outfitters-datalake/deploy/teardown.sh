#!/usr/bin/env bash
# Remove everything deploy.sh created (end of every Learner Lab session = budget hygiene).
# The bucket itself and Aish's ingestion resources are left alone unless DELETE_BUCKET=1.
set -uo pipefail
: "${BUCKET:?export BUCKET first}"
for t in tq-start tq-weekly tq-after-customer tq-after-sales; do aws glue delete-trigger --name $t 2>/dev/null; done
aws glue delete-workflow --name tq-pipeline 2>/dev/null
for j in tq-raw-to-trusted-customer tq-raw-to-trusted-pos tq-raw-to-trusted-ecommerce tq-trusted-to-curated; do
  aws glue delete-job --job-name $j >/dev/null 2>&1; done
aws events remove-targets --rule tq-glue-job-failed --ids sns 2>/dev/null; aws events delete-rule --name tq-glue-job-failed 2>/dev/null
aws cloudwatch delete-alarms --alarm-names tq-quarantine-spike-pos tq-quarantine-spike-ecommerce 2>/dev/null
TOPIC=$(aws sns list-topics --query "Topics[?ends_with(TopicArn,':tq-pipeline-alerts')].TopicArn" --output text)
[[ -n "$TOPIC" ]] && aws sns delete-topic --topic-arn "$TOPIC"
aws athena delete-work-group --work-group thornquist-wg --recursive-delete-option 2>/dev/null
if [[ "${DELETE_BUCKET:-0}" == "1" ]]; then
  aws s3api delete-bucket-policy --bucket "$BUCKET"     # RawIsImmutable would block the delete otherwise
  aws s3 rm "s3://${BUCKET}" --recursive && aws s3api delete-bucket --bucket "$BUCKET"
fi
echo "Teardown complete. Glue Data Catalog tables are free and can stay."
