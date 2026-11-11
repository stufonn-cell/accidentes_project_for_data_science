#!/usr/bin/env bash
# Removes everything the project created in AWS: stops running executions,
# empties the bucket and deletes the stack (bucket, Glue jobs, crawler,
# database and tables, state machine, schedule, SNS topic, Athena
# workgroup, IAM roles and the Power BI user). Safe to run again if it fails halfway.
#
# Nothing is lost for good: the code and the raw CSV are in this repo,
# so deploy.sh + run.sh rebuild the whole lake.
#
# Usage:
#   infra/scripts/destroy.sh       # asks for confirmation
#   infra/scripts/destroy.sh -y    # no questions

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

check_aws
check_serverless
BUCKET="$(bucket_name)"

if [[ "${1:-}" != "-y" ]]; then
  echo "This deletes the stack $STACK and every object in s3://$BUCKET."
  read -r -p "Type 'si' to continue: " ANSWER
  [[ "$ANSWER" == "si" ]] || { echo "Cancelled"; exit 0; }
fi

if stack_exists; then
  MACHINE="$(stack_output StateMachineArn)"
  if [[ -n "$MACHINE" && "$MACHINE" != "None" ]]; then
    log "Stopping running pipeline executions"
    for EXECUTION in $(aws stepfunctions list-executions --state-machine-arn "$MACHINE" \
        --status-filter RUNNING --query 'executions[].executionArn' --output text); do
      aws stepfunctions stop-execution --execution-arn "$EXECUTION" >/dev/null
      echo "Stopped $EXECUTION"
    done
  fi
fi

# CloudFormation cannot delete a user that has access keys it did not create
POWERBI_USER="$STACK-powerbi"
if aws iam get-user --user-name "$POWERBI_USER" >/dev/null 2>&1; then
  log "Deleting the access keys of $POWERBI_USER"
  for KEY in $(aws iam list-access-keys --user-name "$POWERBI_USER"       --query 'AccessKeyMetadata[].AccessKeyId' --output text); do
    aws iam delete-access-key --user-name "$POWERBI_USER" --access-key-id "$KEY"
    echo "Deleted $KEY"
  done
fi

# CloudFormation cannot delete a bucket that still has objects
if bucket_exists "$BUCKET"; then
  log "Emptying s3://$BUCKET"
  aws s3 rm "s3://$BUCKET" --recursive --only-show-errors
fi

if stack_exists; then
  log "Removing the stack $STACK (takes 1 to 3 minutes)"
  (cd "$INFRA_DIR" && serverless remove --region "$REGION")
else
  log "The stack $STACK does not exist, nothing to remove"
fi

log "Checking that nothing is left"
LEFT=0
if stack_exists; then echo "The stack still exists"; LEFT=1; fi
if bucket_exists "$BUCKET"; then echo "The bucket still exists"; LEFT=1; fi
[[ "$LEFT" == 0 ]] || fail "Something was not removed. Run this script again or check CloudFormation in the console."

echo "All removed. What remains costs close to nothing and is shared with other projects:"
echo "  - Glue logs in CloudWatch (/aws-glue/jobs/* groups, a few KB)"
echo "  - The Serverless deployment bucket (serverless-framework-deployments-*), reused by the next deploy"
echo "To bring it back: infra/scripts/deploy.sh && infra/scripts/run.sh"
