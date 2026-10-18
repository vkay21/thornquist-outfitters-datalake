#!/usr/bin/env bash
# Remove what deploy.sh created (end of a Learner Lab session = budget hygiene).
# Aish's resources (bucket, crawlers, Lambda, thornquist-pos-raw-to-trusted,
# thornquist-customer-landing-to-raw, thornquist_retail) are NEVER touched.
set -uo pipefail
for t in thornquist-wf-start thornquist-wf-weekly thornquist-wf-after-customer thornquist-wf-after-sales; do
  aws glue delete-trigger --name $t 2>/dev/null; done
aws glue delete-workflow --name thornquist-pipeline 2>/dev/null
for j in thornquist-customer-raw-to-trusted thornquist-ecommerce-raw-to-trusted thornquist-pos-dq-gate thornquist-trusted-to-curated; do
  aws glue delete-job --job-name $j >/dev/null 2>&1; done
aws events remove-targets --rule thornquist-glue-job-failed --ids sns 2>/dev/null
aws events delete-rule --name thornquist-glue-job-failed 2>/dev/null
aws cloudwatch delete-alarms --alarm-names thornquist-quarantine-spike-pos thornquist-quarantine-spike-ecommerce 2>/dev/null
TOPIC=$(aws sns list-topics --query "Topics[?ends_with(TopicArn,':thornquist-pipeline-alerts')].TopicArn" --output text)
[[ -n "$TOPIC" ]] && aws sns delete-topic --topic-arn "$TOPIC"
aws athena delete-work-group --work-group thornquist-wg --recursive-delete-option 2>/dev/null
echo "Teardown complete. S3 data and Glue Data Catalog tables are kept (free / needed for evidence)."
