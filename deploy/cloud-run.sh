#!/usr/bin/env bash
# Deploy If I Disappear to Google Cloud Run, with secrets in Secret Manager and the
# household data on a Cloud Storage bucket mounted at /data.
#
#   PROJECT=my-project REGION=asia-south1 BUCKET=my-iid-data ./deploy/cloud-run.sh
#
# Create the secrets once (values are read from your terminal, never from this file):
#   printf '%s' "$KEY" | gcloud secrets create iid-model-api-key --data-file=-
#   printf '%s' "$(openssl rand -base64 32)" | gcloud secrets create iid-link-secret --data-file=-
set -euo pipefail
: "${PROJECT:?set PROJECT}" "${REGION:=asia-south1}" "${BUCKET:?set BUCKET}" "${SERVICE:=if-i-disappear}"

gcloud config set project "$PROJECT" >/dev/null
gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1 || gcloud storage buckets create "gs://$BUCKET" --location="$REGION" --uniform-bucket-level-access

gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --execution-environment gen2 \
  --cpu 2 --memory 2Gi \
  --no-cpu-throttling \
  --min-instances 0 --max-instances 1 \
  --timeout 900 \
  --add-volume name=data,type=cloud-storage,bucket="$BUCKET" \
  --add-volume-mount volume=data,mount-path=/data \
  --set-env-vars IID_DATA_DIR=/data,IID_MODE=live,IID_DAILY_BUDGET_USD=5 \
  --set-secrets MODEL_API_KEY=iid-model-api-key:latest,IID_LINK_SECRET=iid-link-secret:latest

URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')
gcloud run services update "$SERVICE" --region "$REGION" --update-env-vars IID_PUBLIC_BASE_URL="$URL" >/dev/null
echo "Deployed: $URL"
echo "Check it: curl -s $URL/api/health"
