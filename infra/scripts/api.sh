#!/usr/bin/env bash
# Prediction API on AWS: Lambda (container image) behind an API Gateway HTTP API.
# It needs the lake deployed (deploy.sh) and the pipeline run once (run.sh),
# because the API reads the model from s3://<bucket>/gold/modelos/.
#
# Usage:
#   infra/scripts/api.sh deploy              # build the image, deploy and test
#   infra/scripts/api.sh deploy <version>    # serve a registered model version
#   infra/scripts/api.sh test                # call the live endpoint with curl
#   infra/scripts/api.sh register            # copy the current model to registro_modelos/<version>/
#   infra/scripts/api.sh remove              # delete the API stack and its images
#
# The API key comes from API_KEY in infra/.env. Without it, deploy creates a
# random one and prints it once.

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

API_STACK="$STACK-api"
API_DIR="$INFRA_DIR/api"
EVIDENCE="$ROOT_DIR/build/api_aws_smoke.txt"

api_stack_exists() {
  aws cloudformation describe-stacks --stack-name "$API_STACK" >/dev/null 2>&1
}

api_url() {
  aws cloudformation describe-stacks --stack-name "$API_STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='HttpApiUrl'].OutputValue" --output text
}

deployed_key() {
  aws lambda get-function-configuration --function-name "$API_STACK" \
    --query 'Environment.Variables.API_KEY' --output text 2>/dev/null || true
}

# Reads one field of a JSON document from stdin
json_field() {
  "$PYTHON" -c "import json,sys; print(json.load(sys.stdin).get('$1', ''))"
}

# call <expected status> <description> <curl arguments...>
call() {
  local expected="$1" description="$2"
  shift 2
  local status
  status="$(curl -s -o "$BODY" -w '%{http_code}' --max-time 60 "$@")"
  printf '%s -> HTTP %s\n%s\n\n' "$description" "$status" "$(cat "$BODY")" | tee -a "$EVIDENCE"
  [[ "$status" == "$expected" ]] || fail "$description: expected HTTP $expected, got $status"
}

smoke_test() {
  api_stack_exists || fail "The stack $API_STACK does not exist. Run: infra/scripts/api.sh deploy"
  local url key
  url="$(api_url)"
  [[ -n "$url" && "$url" != "None" ]] || fail "The stack $API_STACK has no HttpApiUrl output"
  key="${API_KEY:-$(deployed_key)}"
  [[ -n "$key" && "$key" != "None" ]] || fail "No API key: set API_KEY in infra/.env"

  mkdir -p "$ROOT_DIR/build"
  BODY="$(mktemp)"
  trap 'rm -f "$BODY"' EXIT
  printf 'Smoke test of %s on %s\n\n' "$url" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$EVIDENCE"

  local accident='{"tipo":"MOTOCICLETA","marca":"AKT","modelo":2023,"fecha":"06/2024","departamento":"ANTIOQUIA","autoridad":"DIRECCION DE TRANSITO Y TRANSPORTE"}'

  log "Testing $url"
  # The first call starts the container and loads the model: it can take 10 to 20 seconds
  call 200 "GET /health" "$url/health"
  [[ "$(json_field estado < "$BODY")" == "ok" ]] || fail "/health did not answer estado ok"
  local version
  version="$(json_field version < "$BODY")"

  call 401 "POST /predict without API key" -X POST "$url/predict" \
    -H "Content-Type: application/json" -d "$accident"

  call 200 "POST /predict" -X POST "$url/predict" \
    -H "Content-Type: application/json" -H "X-API-Key: $key" -d "$accident"
  "$PYTHON" -c "
import json, sys
body = json.load(sys.stdin)
assert 0 <= body['probabilidad'] <= 1, body
assert body['alerta'] == (body['probabilidad'] >= body['umbral_decision']), body
assert body['version'] == '$version', body
" < "$BODY" || fail "The prediction is not consistent"

  call 422 "POST /predict with an invalid date" -X POST "$url/predict" \
    -H "Content-Type: application/json" -H "X-API-Key: $key" -d '{"tipo": "MOTOCICLETA", "fecha": "ayer", "departamento": "ANTIOQUIA", "autoridad": "X"}'

  call 200 "POST /predict/batch" -X POST "$url/predict/batch" \
    -H "Content-Type: application/json" -H "X-API-Key: $key" -d "{\"vehiculos\": [$accident, $accident]}"
  [[ "$(json_field total < "$BODY")" == "2" ]] || fail "The batch did not return 2 predictions"

  log "The API works. Model version $version. Evidence saved in build/api_aws_smoke.txt"
  echo "Docs: $url/docs"
}

deploy() {
  local model_version="${1:-}"
  check_aws
  check_serverless
  command -v docker >/dev/null 2>&1 || fail "Docker not found. Serverless needs it to build the image."
  docker info >/dev/null 2>&1 || fail "Docker is not running. Start Docker Desktop."

  local bucket
  bucket="$(bucket_name)"
  bucket_exists "$bucket" || fail "The lake s3://$bucket does not exist. Run: infra/scripts/deploy.sh"
  aws s3api head-object --bucket "$bucket" --key gold/modelos/metricas.json >/dev/null 2>&1 \
    || fail "There is no model in s3://$bucket/gold/modelos/. Run: infra/scripts/run.sh"
  if [[ -n "$model_version" ]]; then
    aws s3api head-object --bucket "$bucket" --key "registro_modelos/$model_version/modelo.joblib" >/dev/null 2>&1 \
      || fail "Version $model_version is not in s3://$bucket/registro_modelos/. Run: infra/scripts/api.sh register"
  fi

  # Keep the key of a previous deploy, so clients do not break
  if [[ -z "${API_KEY:-}" ]]; then
    API_KEY="$(deployed_key)"
    if [[ -z "$API_KEY" || "$API_KEY" == "None" ]]; then
      API_KEY="$("$PYTHON" -c "import secrets; print(secrets.token_urlsafe(32))")"
      echo "New API key (shown once, save it as API_KEY in infra/.env): $API_KEY"
    fi
  fi

  log "Building the image and deploying $API_STACK to $REGION (5 to 10 minutes the first time)"
  (cd "$API_DIR" && serverless deploy --region "$REGION" \
    --param="apiKey=$API_KEY" --param="modelVersion=$model_version")

  smoke_test
}

register() {
  check_aws
  local bucket
  bucket="$(bucket_name)"
  bucket_exists "$bucket" || fail "The lake s3://$bucket does not exist. Run: infra/scripts/deploy.sh"
  log "Registering the current model of s3://$bucket/gold/modelos/"
  (cd "$ROOT_DIR" && DATA_DIR="s3://$bucket" "$PYTHON" -m api.register_model)
}

remove() {
  check_aws
  check_serverless
  if api_stack_exists; then
    log "Removing the stack $API_STACK"
    # The key is not needed to remove, but the parameter must resolve
    (cd "$API_DIR" && serverless remove --region "$REGION" --param="apiKey=removed")
  else
    log "The stack $API_STACK does not exist, nothing to remove"
  fi
  # Serverless keeps its images in this repository
  local repository="serverless-$API_STACK-dev"
  if aws ecr describe-repositories --repository-names "$repository" >/dev/null 2>&1; then
    log "Deleting the ECR repository $repository"
    aws ecr delete-repository --repository-name "$repository" --force >/dev/null
  fi
  api_stack_exists && fail "The stack $API_STACK still exists. Check CloudFormation in the console."
  echo "The API is removed. The lake is untouched."
}

PYTHON="$(find_python)"

case "${1:-}" in
  deploy) deploy "${2:-}" ;;
  test) check_aws; smoke_test ;;
  register) register ;;
  remove) remove ;;
  *) echo "Usage: infra/scripts/api.sh deploy [version] | test | register | remove"; exit 1 ;;
esac
