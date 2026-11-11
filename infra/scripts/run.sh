#!/usr/bin/env bash
# Starts the pipeline in Step Functions and waits until it finishes.
# Exits with an error if the pipeline fails, so it works as a smoke test.
#
# Usage: infra/scripts/run.sh

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

check_aws
stack_exists || fail "The stack $STACK does not exist. Deploy it first with infra/scripts/deploy.sh"

MACHINE="$(stack_output StateMachineArn)"
BUCKET="$(stack_output BucketName)"

log "Starting the pipeline"
EXECUTION="$(aws stepfunctions start-execution --state-machine-arn "$MACHINE" \
  --name "manual-$(date +%Y%m%d-%H%M%S)" --query executionArn --output text)"
echo "Execution: $EXECUTION"
echo "Console:   https://$REGION.console.aws.amazon.com/states/home?region=$REGION#/v2/executions/details/$EXECUTION"
echo "Each Glue stage takes about 2 to 4 minutes (most of it installing pandas and scikit-learn)."

START=$(date +%s)
while true; do
  STATUS="$(aws stepfunctions describe-execution --execution-arn "$EXECUTION" --query status --output text)"
  ELAPSED=$(( $(date +%s) - START ))
  printf '  %02d:%02d  %s\n' $((ELAPSED / 60)) $((ELAPSED % 60)) "$STATUS"
  [[ "$STATUS" == "RUNNING" ]] || break
  sleep 30
done

if [[ "$STATUS" != "SUCCEEDED" ]]; then
  aws stepfunctions describe-execution --execution-arn "$EXECUTION" --query '[error, cause]' --output text || true
  fail "The pipeline ended as $STATUS. Open the console link above and the logs in CloudWatch /aws-glue/jobs/error."
fi

log "Pipeline OK. Contents of the gold layer:"
aws s3 ls "s3://$BUCKET/gold/" --recursive --human-readable --summarize | tail -n 25

log "Model metrics (gold/modelos/metricas.json):"
aws s3 cp "s3://$BUCKET/gold/modelos/metricas.json" - | head -n 40

# The pipeline starts the crawler without waiting for it. Wait here so the
# tables are ready for Athena and Power BI when this script ends.
log "Waiting for the crawler to register the tables (about 2 minutes)"
CRAWLER="$STACK-crawler"
sleep 15
while [[ "$(aws glue get-crawler --name "$CRAWLER" --query Crawler.State --output text)" != "READY" ]]; do
  sleep 20
done
LAST="$(aws glue get-crawler --name "$CRAWLER" --query Crawler.LastCrawl.Status --output text)"
[[ "$LAST" == "SUCCEEDED" ]] || echo "Warning: the last crawl ended as $LAST. Check the crawler in the Glue console."
aws glue get-tables --database-name "$(stack_output GlueDatabase)" --query 'TableList[].Name' --output text | tr '\t' '\n' | sort

log "Done. To connect Power BI run: infra/scripts/powerbi.sh"
