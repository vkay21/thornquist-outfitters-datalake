#!/usr/bin/env bash
# Run every sql/analytics/*.sql in Athena and save results to evidence/athena_run/ (CSV).
# Usage (CloudShell, repo root):  export BUCKET=...; bash deploy/run_queries.sh
set -euo pipefail
: "${BUCKET:?export BUCKET first}"
WG=thornquist-wg
OUT=evidence/athena_run; mkdir -p "$OUT"
cd "$(dirname "$0")/.."
echo "query,state,data_scanned_bytes,engine_ms" > "$OUT/_stats.csv"
for f in sql/analytics/*.sql; do
  name=$(basename "$f" .sql)
  qid=$(aws athena start-query-execution --work-group "$WG" --query-string "file://$f" --query QueryExecutionId --output text)
  while true; do
    state=$(aws athena get-query-execution --query-execution-id "$qid" --query QueryExecution.Status.State --output text)
    [[ "$state" =~ ^(SUCCEEDED|FAILED|CANCELLED)$ ]] && break; sleep 1
  done
  stats=$(aws athena get-query-execution --query-execution-id "$qid" \
    --query '[QueryExecution.Statistics.DataScannedInBytes,QueryExecution.Statistics.EngineExecutionTimeInMillis]' --output text | tr '\t' ',')
  echo "${name},${state},${stats}" >> "$OUT/_stats.csv"
  if [[ "$state" == "SUCCEEDED" ]]; then
    aws s3 cp "s3://${BUCKET}/athena-results/${qid}.csv" "$OUT/${name}.csv" --quiet
    echo "OK   $name  (scanned ${stats%%,*} bytes)"; head -6 "$OUT/${name}.csv" | column -s, -t; echo
  else
    echo "FAIL $name: $(aws athena get-query-execution --query-execution-id "$qid" --query QueryExecution.Status.StateChangeReason --output text)"
  fi
done
echo "Saved to $OUT/  - commit these as evidence (resources won't survive the lab session)."
