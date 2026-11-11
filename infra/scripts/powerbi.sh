#!/usr/bin/env bash
# Gets everything Power BI needs to read the gold layer through Athena:
# checks that the tables exist and creates an access key for the read-only
# user accidentes-envigado-powerbi. Prints the values for the ODBC DSN.
#
# Each run replaces the previous key of that user, so run it again if the
# key is lost. Run it after deploy.sh and run.sh.
#
# Usage: infra/scripts/powerbi.sh

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

check_aws
stack_exists || fail "The stack $STACK does not exist. Deploy it first with infra/scripts/deploy.sh"

USER_NAME="$(stack_output PowerBIUser)"
DATABASE="$(stack_output GlueDatabase)"
WORKGROUP="$(stack_output AthenaWorkGroup)"
BUCKET="$(stack_output BucketName)"
[[ -n "$USER_NAME" && "$USER_NAME" != "None" ]] || fail "The stack has no PowerBIUser output. Run infra/scripts/deploy.sh again."

log "Tables in the database $DATABASE"
TABLES="$(aws glue get-tables --database-name "$DATABASE" --query 'TableList[].Name' --output text)"
if [[ -z "$TABLES" ]]; then
  echo "No tables yet. Run infra/scripts/run.sh and wait for the crawler to finish."
else
  echo "$TABLES" | tr '\t' '\n' | sort
fi

log "Replacing the access key of $USER_NAME"
for KEY in $(aws iam list-access-keys --user-name "$USER_NAME" --query 'AccessKeyMetadata[].AccessKeyId' --output text); do
  aws iam delete-access-key --user-name "$USER_NAME" --access-key-id "$KEY"
  echo "Deleted old key $KEY"
done
read -r KEY_ID KEY_SECRET < <(aws iam create-access-key --user-name "$USER_NAME" \
  --query 'AccessKey.[AccessKeyId, SecretAccessKey]' --output text)

cat <<INFO

==> ODBC settings for Power BI (Amazon Athena ODBC driver 2.x)

  Data Source Name:     accidentes-envigado
  Region:               $REGION
  Catalog:              AwsDataCatalog
  Database:             $DATABASE
  Workgroup:            $WORKGROUP
  S3 Output Location:   s3://$BUCKET/athena-results/
  Authentication type:  IAM Credentials
  User (access key):    $KEY_ID
  Password (secret):    $KEY_SECRET

The secret is shown only this once and only grants read access to gold.
Do not commit it. Step by step instructions: README, section "Power BI".
INFO
