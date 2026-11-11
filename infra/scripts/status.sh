#!/usr/bin/env bash
# Shows what of the project exists in AWS right now.
# Use it after destroy.sh to confirm nothing is left.
#
# Usage: infra/scripts/status.sh

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

check_aws
BUCKET="$(bucket_name)"

log "Stack"
if stack_exists; then
  aws cloudformation describe-stacks --stack-name "$STACK" --query 'Stacks[0].StackStatus' --output text
else
  echo "Does not exist"
fi

log "Bucket $BUCKET"
if bucket_exists "$BUCKET"; then
  aws s3 ls "s3://$BUCKET" --recursive --summarize | tail -n 2
else
  echo "Does not exist"
fi

log "Schedule"
aws scheduler get-schedule --name "$STACK-monthly" --query State --output text 2>/dev/null || echo "Does not exist"

log "Glue jobs"
JOBS="$(aws glue list-jobs --query "JobNames[?starts_with(@, '$STACK-')]" --output text 2>/dev/null || true)"
echo "${JOBS:-None}"

log "Running pipeline executions"
if stack_exists; then
  aws stepfunctions list-executions --state-machine-arn "$(stack_output StateMachineArn)" \
    --status-filter RUNNING --query 'length(executions)' --output text
else
  echo "0"
fi

log "Tables in the catalog"
aws glue get-tables --database-name accidentes_envigado --query 'TableList[].Name' --output text 2>/dev/null | tr '\t' '\n' || echo "None"
