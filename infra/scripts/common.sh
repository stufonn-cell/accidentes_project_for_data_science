#!/usr/bin/env bash
# Shared settings for the deploy, run, status and destroy scripts.
# Sourced by them, not run directly.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INFRA_DIR="$ROOT_DIR/infra"
STACK="accidentes-envigado"
REGION="us-east-1"

# Credentials can live in infra/.env (git-ignored), see infra/.env.example
if [[ -f "$INFRA_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$INFRA_DIR/.env"
  set +a
fi

export AWS_DEFAULT_REGION="$REGION"
export AWS_REGION="$REGION"
export AWS_PAGER=""
# Git Bash on Windows rewrites arguments that look like paths: turn it off
export MSYS_NO_PATHCONV=1

# Windows programs (python.exe, aws.exe) do not understand Git Bash paths
# like /c/folder, and MSYS_NO_PATHCONV stops Git Bash from converting them.
# Use this for every local file passed to them.
native_path() {
  if command -v cygpath >/dev/null 2>&1; then cygpath -w "$1"; else echo "$1"; fi
}

log() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

find_python() {
  for candidate in python python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import sys; sys.exit(sys.version_info < (3, 9))" 2>/dev/null; then
      echo "$candidate"
      return
    fi
  done
  fail "Python 3.9 or newer not found"
}

check_aws() {
  command -v aws >/dev/null 2>&1 || fail "AWS CLI not found. Install it (winget install Amazon.AWSCLI) or use the dev container of the labs."
  aws sts get-caller-identity --query Account --output text >/dev/null 2>&1 \
    || fail "AWS credentials not valid. Fill infra/.env or run aws configure."
}

check_serverless() {
  command -v serverless >/dev/null 2>&1 || fail "Serverless Framework not found. Install it with: npm install -g serverless"
  if [[ -z "${SERVERLESS_ACCESS_KEY:-}" ]]; then
    echo "Note: SERVERLESS_ACCESS_KEY is not set. Serverless v4 will ask you to log in if you have not done it before."
  fi
}

account_id() { aws sts get-caller-identity --query Account --output text; }

bucket_name() { echo "$STACK-lake-$(account_id)"; }

stack_exists() {
  aws cloudformation describe-stacks --stack-name "$STACK" >/dev/null 2>&1
}

stack_output() {
  aws cloudformation describe-stacks --stack-name "$STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}

bucket_exists() {
  aws s3api head-bucket --bucket "$1" >/dev/null 2>&1
}
