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
SERVICE_ACCOUNT=""  # Uses default compute SA if empty

# Secret names (all prefixed to avoid collision with PowerDataChat)
SECRET_PREFIX="SOCIAL_POSTER"
SECRETS=(
    "GEMINI_API_KEY"
    "LINKEDIN_ACCESS_TOKEN"
    "LINKEDIN_PERSON_URN"
    "LINKEDIN_CLIENT_ID"
    "LINKEDIN_CLIENT_SECRET"
    "FACEBOOK_PAGE_ID"
    "FACEBOOK_PAGE_ACCESS_TOKEN"
    "FACEBOOK_APP_ID"
    "FACEBOOK_APP_SECRET"
    "X_API_KEY"
    "X_API_SECRET"
    "X_ACCESS_TOKEN"
    "X_ACCESS_TOKEN_SECRET"
)

echo "============================================================"
echo "  SOCIAL-POSTER DEPLOYMENT"
echo "============================================================"
echo ""
echo "  WARNING: This deploys the social-poster job ONLY."
echo "  It does NOT affect the main PowerDataChat service."
echo ""
echo "  Project:  ${PROJECT_ID}"
echo "  Job Name: ${JOB_NAME}"
echo "  Region:   ${REGION}"
echo ""
echo "============================================================"
echo ""

# Step 1: Authenticate
echo "[1/7] Authenticating with GCP..."
gcloud auth login
gcloud config set project "${PROJECT_ID}"

# Step 2: Build and push container image
echo ""
echo "[2/7] Building container image..."
gcloud builds submit --tag "${IMAGE}" .

# Step 3: Create secrets in Secret Manager (skip if they already exist)
echo ""
echo "[3/7] Setting up secrets in Secret Manager..."
echo "  (You'll be prompted to enter values for secrets that don't exist yet)"

SECRET_ENV_ARGS=""
for SECRET_NAME in "${SECRETS[@]}"; do
    FULL_SECRET_NAME="${SECRET_PREFIX}_${SECRET_NAME}"

    # Check if secret exists
    if gcloud secrets describe "${FULL_SECRET_NAME}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
        echo "  Secret ${FULL_SECRET_NAME} already exists, skipping creation"
    else
        echo "  Creating secret: ${FULL_SECRET_NAME}"
        read -rsp "  Enter value for ${SECRET_NAME} (or press Enter to skip): " SECRET_VALUE
        echo ""

        if [ -n "${SECRET_VALUE}" ]; then
            echo -n "${SECRET_VALUE}" | gcloud secrets create "${FULL_SECRET_NAME}" \
                --data-file=- \
                --project="${PROJECT_ID}" \
                --replication-policy="automatic"
        else
            # Create empty secret as placeholder
            echo -n "" | gcloud secrets create "${FULL_SECRET_NAME}" \
                --data-file=- \
                --project="${PROJECT_ID}" \
                --replication-policy="automatic"
            echo "  (Created empty placeholder for ${FULL_SECRET_NAME})"
        fi
    fi

    # Build the --set-secrets argument: ENV_VAR=SECRET_NAME:latest
    SECRET_ENV_ARGS="${SECRET_ENV_ARGS}${SECRET_NAME}=${FULL_SECRET_NAME}:latest,"
done

# Remove trailing comma
SECRET_ENV_ARGS="${SECRET_ENV_ARGS%,}"

# Step 4: Deploy as Cloud Run Job
echo ""
echo "[4/7] Deploying Cloud Run Job: ${JOB_NAME}..."

# Check if job already exists
if gcloud run jobs describe "${JOB_NAME}" --region="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    echo "  Job exists, updating..."
    gcloud run jobs update "${JOB_NAME}" \
        --image="${IMAGE}" \
        --region="${REGION}" \
        --project="${PROJECT_ID}" \
        --set-secrets="${SECRET_ENV_ARGS}" \
        --memory="512Mi" \
        --task-timeout="30m" \
        --max-retries=1
else
    echo "  Creating new job..."
    gcloud run jobs create "${JOB_NAME}" \
        --image="${IMAGE}" \
        --region="${REGION}" \
        --project="${PROJECT_ID}" \
        --set-secrets="${SECRET_ENV_ARGS}" \
        --memory="512Mi" \
        --task-timeout="30m" \
        --max-retries=1
fi

# Step 5: Set up Cloud Scheduler to trigger the job every 6 hours
echo ""
echo "[5/7] Setting up Cloud Scheduler: ${SCHEDULER_NAME}..."

# Get the job URI for the scheduler
JOB_URI="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run"

if gcloud scheduler jobs describe "${SCHEDULER_NAME}" --location="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    echo "  Scheduler job exists, updating..."
    gcloud scheduler jobs update http "${SCHEDULER_NAME}" \
        --location="${REGION}" \
        --project="${PROJECT_ID}" \
        --schedule="0 */6 * * *" \
        --uri="${JOB_URI}" \
        --http-method=POST \
        --oauth-service-account-email="${PROJECT_ID}@appspot.gserviceaccount.com" \
        --time-zone="UTC"
else
    echo "  Creating new scheduler job..."
    gcloud scheduler jobs create http "${SCHEDULER_NAME}" \
        --location="${REGION}" \
        --project="${PROJECT_ID}" \
        --schedule="0 */6 * * *" \
        --uri="${JOB_URI}" \
        --http-method=POST \
        --oauth-service-account-email="${PROJECT_ID}@appspot.gserviceaccount.com" \
        --time-zone="UTC"
fi

# Step 6: Verify deployment
echo ""
echo "[6/7] Verifying deployment..."
gcloud run jobs describe "${JOB_NAME}" --region="${REGION}" --project="${PROJECT_ID}" --format="table(name,status)"

# Step 7: Done
echo ""
echo "============================================================"
echo "  DEPLOYMENT COMPLETE"
echo "============================================================"
echo ""
echo "  Job:       ${JOB_NAME}"
echo "  Scheduler: ${SCHEDULER_NAME} (every 6 hours)"
echo "  Image:     ${IMAGE}"
echo ""
echo "  To run manually:"
echo "    gcloud run jobs execute ${JOB_NAME} --region=${REGION}"
echo ""
echo "  To view logs:"
echo "    gcloud logging read 'resource.labels.job_name=${JOB_NAME}' --limit=50"
echo ""
echo "  Deployed social-poster job."
echo "  Main datachat service was NOT modified."
echo ""
echo "============================================================"
