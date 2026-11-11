#!/usr/bin/env bash
# Deploys everything to AWS: the stack, the job code and the raw CSV.
# Safe to run as many times as you want: it updates what already exists.
#
# Usage:
#   infra/scripts/deploy.sh                                # schedule disabled
#   infra/scripts/deploy.sh --param="scheduleState=ENABLED"
#
# Set ALERT_EMAIL in infra/.env to get an email when the pipeline fails.

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

PYTHON="$(find_python)"
check_aws
check_serverless

log "Packing src into build/src.zip"
"$PYTHON" "$(native_path "$INFRA_DIR/scripts/build_zip.py")"

EXTRA_PARAMS=()
if [[ -n "${ALERT_EMAIL:-}" ]]; then
  EXTRA_PARAMS+=("--param=alertEmail=$ALERT_EMAIL")
fi

log "Deploying the stack $STACK to $REGION (takes 1 to 3 minutes)"
(cd "$INFRA_DIR" && serverless deploy --region "$REGION" ${EXTRA_PARAMS[@]+"${EXTRA_PARAMS[@]}"} "$@")

BUCKET="$(stack_output BucketName)"
[[ -n "$BUCKET" && "$BUCKET" != "None" ]] || fail "The stack has no BucketName output"

log "Uploading the job code to s3://$BUCKET/scripts/"
aws s3 cp "$(native_path "$ROOT_DIR/glue_jobs/run_stage.py")" "s3://$BUCKET/scripts/run_stage.py"
aws s3 cp "$(native_path "$ROOT_DIR/build/src.zip")" "s3://$BUCKET/scripts/src.zip"

log "Uploading the raw CSV to s3://$BUCKET/raw/"
aws s3 cp "$(native_path "$ROOT_DIR/data/raw/accidentalidad_envigado.csv")" "s3://$BUCKET/raw/accidentalidad_envigado.csv"

log "Deployed. Run the pipeline with: infra/scripts/run.sh"
