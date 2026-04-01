#!/usr/bin/env bash
# deploy_gcp.sh — Deploy social-poster as a Cloud Run Job on GCP
#
# This deploys the social-poster job ONLY.
# It does NOT affect the main PowerDataChat (datachat) service.
#
# Usage:
#   chmod +x deploy_gcp.sh
#   ./deploy_gcp.sh

set -euo pipefail

PROJECT_ID="datachat-478206"
REGION="us-central1"
JOB_NAME="social-poster"
IMAGE="gcr.io/${PROJECT_ID}/social-poster"
SCHEDULER_NAME="social-poster-trigger"
GCS_BUCKET="${PROJECT_ID}-social-poster-data"

# Secret mappings: ENV_VAR_NAME -> value read from .env
# All secrets in Secret Manager are prefixed with SOCIAL_POSTER_
declare -A SECRETS_MAP
SECRETS_MAP=(
    [GEMINI_API_KEY]=""
    [LINKEDIN_ACCESS_TOKEN]=""
    [LINKEDIN_PERSON_URN]=""
    [LINKEDIN_CLIENT_ID]=""
    [LINKEDIN_CLIENT_SECRET]=""
    [FACEBOOK_PAGE_ID]=""
    [FACEBOOK_PAGE_ACCESS_TOKEN]=""
    [FACEBOOK_APP_ID]=""
    [FACEBOOK_APP_SECRET]=""
    [X_API_KEY]=""
    [X_API_SECRET]=""
    [X_ACCESS_TOKEN]=""
    [X_ACCESS_TOKEN_SECRET]=""
)

echo "============================================================"
echo "  SOCIAL-POSTER DEPLOYMENT"
echo "============================================================"
echo ""
echo "  WARNING: This deploys the social-poster job ONLY."
echo "  It does NOT affect the main PowerDataChat service."
echo ""
echo "  Project:    ${PROJECT_ID}"
echo "  Job Name:   ${JOB_NAME}"
echo "  Region:     ${REGION}"
echo "  GCS Bucket: ${GCS_BUCKET}"
echo ""
echo "============================================================"
echo ""

# ------------------------------------------------------------------
# Step 1: Authentication
# ------------------------------------------------------------------
echo "[1/8] Authenticating with GCP..."
gcloud auth login
gcloud config set project "${PROJECT_ID}"

# ------------------------------------------------------------------
# Step 2: Enable required APIs
# ------------------------------------------------------------------
echo ""
echo "[2/8] Enabling required APIs..."
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    cloudscheduler.googleapis.com \
    secretmanager.googleapis.com \
    storage.googleapis.com \
    --quiet

# ------------------------------------------------------------------
# Step 3: Build and push container image
# ------------------------------------------------------------------
echo ""
echo "[3/8] Building container image..."
gcloud builds submit --tag "${IMAGE}" .

# ------------------------------------------------------------------
# Step 4: Read .env and create/update secrets
# ------------------------------------------------------------------
echo ""
echo "[4/8] Setting up secrets in Secret Manager..."

# Read values from .env file
if [ -f .env ]; then
    echo "  Reading values from .env file..."
    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        [[ -z "$key" || "$key" =~ ^# ]] && continue
        # Trim whitespace
        key=$(echo "$key" | xargs)
        value=$(echo "$value" | xargs)
        if [[ -v "SECRETS_MAP[$key]" ]]; then
            SECRETS_MAP[$key]="$value"
        fi
    done < .env
else
    echo "  WARNING: No .env file found. Secrets must already exist in Secret Manager."
fi

# Get project number and service account for IAM bindings
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')
SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

SECRET_ENV_ARGS=""
for ENV_VAR in "${!SECRETS_MAP[@]}"; do
    SECRET_NAME="SOCIAL_POSTER_${ENV_VAR}"
    SECRET_VALUE="${SECRETS_MAP[$ENV_VAR]}"

    # Skip secrets with empty values (don't create empty secrets)
    if [ -z "${SECRET_VALUE}" ]; then
        # Check if secret already exists in Secret Manager
        if gcloud secrets describe "${SECRET_NAME}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
            echo "  ${SECRET_NAME}: exists in Secret Manager (no local value)"
            SECRET_ENV_ARGS="${SECRET_ENV_ARGS}${ENV_VAR}=${SECRET_NAME}:latest,"
        else
            echo "  ${SECRET_NAME}: skipping (empty value, not in Secret Manager)"
        fi
        continue
    fi

    # Create or update the secret
    if gcloud secrets describe "${SECRET_NAME}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
        echo "  ${SECRET_NAME}: updating with new version..."
        echo -n "${SECRET_VALUE}" | gcloud secrets versions add "${SECRET_NAME}" \
            --data-file=- --project="${PROJECT_ID}" --quiet
    else
        echo "  ${SECRET_NAME}: creating..."
        echo -n "${SECRET_VALUE}" | gcloud secrets create "${SECRET_NAME}" \
            --data-file=- \
            --replication-policy=automatic \
            --project="${PROJECT_ID}"

        # Grant Cloud Run service account access
        gcloud secrets add-iam-policy-binding "${SECRET_NAME}" \
            --member="serviceAccount:${SA}" \
            --role="roles/secretmanager.secretAccessor" \
            --project="${PROJECT_ID}" --quiet
    fi

    SECRET_ENV_ARGS="${SECRET_ENV_ARGS}${ENV_VAR}=${SECRET_NAME}:latest,"
done

# Remove trailing comma
SECRET_ENV_ARGS="${SECRET_ENV_ARGS%,}"

if [ -z "${SECRET_ENV_ARGS}" ]; then
    echo ""
    echo "  ERROR: No secrets configured. At minimum GEMINI_API_KEY is required."
    echo "  Create a .env file with your API keys and re-run."
    exit 1
fi

# ------------------------------------------------------------------
# Step 5: Create GCS bucket for DB persistence
# ------------------------------------------------------------------
echo ""
echo "[5/8] Setting up GCS bucket for state persistence..."
if gsutil ls -b "gs://${GCS_BUCKET}" >/dev/null 2>&1; then
    echo "  Bucket gs://${GCS_BUCKET} already exists"
else
    echo "  Creating bucket gs://${GCS_BUCKET}..."
    gsutil mb -l "${REGION}" "gs://${GCS_BUCKET}"
fi

# ------------------------------------------------------------------
# Step 6: Deploy Cloud Run Job
# ------------------------------------------------------------------
echo ""
echo "[6/8] Deploying Cloud Run Job: ${JOB_NAME}..."

JOB_CMD=(
    --image="${IMAGE}"
    --region="${REGION}"
    --project="${PROJECT_ID}"
    --set-secrets="${SECRET_ENV_ARGS}"
    --set-env-vars="GCS_BUCKET=${GCS_BUCKET}"
    --memory="512Mi"
    --task-timeout="600"
    --max-retries=1
)

if gcloud run jobs describe "${JOB_NAME}" --region="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    echo "  Job exists, updating..."
    gcloud run jobs update "${JOB_NAME}" "${JOB_CMD[@]}"
else
    echo "  Creating new job..."
    gcloud run jobs create "${JOB_NAME}" "${JOB_CMD[@]}"
fi

# ------------------------------------------------------------------
# Step 7: Create Cloud Scheduler (every 6 hours)
# ------------------------------------------------------------------
echo ""
echo "[7/8] Setting up Cloud Scheduler: ${SCHEDULER_NAME}..."

JOB_URI="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run"

if gcloud scheduler jobs describe "${SCHEDULER_NAME}" --location="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    echo "  Scheduler job exists, updating..."
    gcloud scheduler jobs update http "${SCHEDULER_NAME}" \
        --location="${REGION}" \
        --project="${PROJECT_ID}" \
        --schedule="0 */6 * * *" \
        --uri="${JOB_URI}" \
        --http-method=POST \
        --oauth-service-account-email="${SA}" \
        --time-zone="UTC"
else
    echo "  Creating new scheduler job..."
    gcloud scheduler jobs create http "${SCHEDULER_NAME}" \
        --location="${REGION}" \
        --project="${PROJECT_ID}" \
        --schedule="0 */6 * * *" \
        --uri="${JOB_URI}" \
        --http-method=POST \
        --oauth-service-account-email="${SA}" \
        --time-zone="UTC"
fi

# ------------------------------------------------------------------
# Step 8: Done
# ------------------------------------------------------------------
echo ""
echo "============================================================"
echo "  DEPLOYMENT COMPLETE"
echo "============================================================"
echo ""
echo "  Job:       ${JOB_NAME}"
echo "  Schedule:  Every 6 hours (0 */6 * * *)"
echo "  Scheduler: ${SCHEDULER_NAME}"
echo "  Image:     ${IMAGE}"
echo "  GCS:       gs://${GCS_BUCKET}"
echo ""
echo "  Main datachat service was NOT modified."
echo ""
echo "  Useful commands:"
echo "    Manual run:    gcloud run jobs execute ${JOB_NAME} --region=${REGION}"
echo "    View logs:     gcloud logging read \"resource.type=cloud_run_job AND resource.labels.job_name=${JOB_NAME}\" --limit=50"
echo "    View runs:     gcloud run jobs executions list --job=${JOB_NAME} --region=${REGION}"
echo "    Update image:  gcloud run jobs update ${JOB_NAME} --image=${IMAGE} --region=${REGION}"
echo ""
echo "============================================================"
