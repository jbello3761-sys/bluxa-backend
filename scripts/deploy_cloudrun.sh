#!/usr/bin/env bash
set -euo pipefail

# BLuxA Corp - Manual Cloud Run Deployment Script
# Usage: ./scripts/deploy_cloudrun.sh [environment]

ENVIRONMENT=${1:-production}
PROJECT_ID=${GCP_PROJECT_ID:-""}
REGION=${GCP_REGION:-"us-east4"}
SERVICE_NAME="bluxa-api"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 BLuxA Corp API Deployment Script${NC}"
echo -e "${BLUE}Environment: ${ENVIRONMENT}${NC}"
echo -e "${BLUE}Region: ${REGION}${NC}"
echo ""

# Check prerequisites
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}❌ Error: GCP_PROJECT_ID environment variable not set${NC}"
    echo "Please set: export GCP_PROJECT_ID=your-project-id"
    exit 1
fi

if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}❌ Error: gcloud CLI not found${NC}"
    echo "Please install: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Error: Docker not found${NC}"
    echo "Please install Docker"
    exit 1
fi

# Check if logged into gcloud
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo -e "${RED}❌ Error: Not authenticated with gcloud${NC}"
    echo "Please run: gcloud auth login"
    exit 1
fi

# Set project
echo -e "${YELLOW}📋 Setting GCP project...${NC}"
gcloud config set project $PROJECT_ID

# Enable required APIs
echo -e "${YELLOW}🔧 Enabling required APIs...${NC}"
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com

# Configure Docker
echo -e "${YELLOW}🐳 Configuring Docker...${NC}"
gcloud auth configure-docker

# Build image
IMAGE_TAG="gcr.io/$PROJECT_ID/$SERVICE_NAME:$(date +%Y%m%d-%H%M%S)"
echo -e "${YELLOW}🏗️  Building Docker image: $IMAGE_TAG${NC}"
docker build -t $IMAGE_TAG .

# Push image
echo -e "${YELLOW}📤 Pushing image to Container Registry...${NC}"
docker push $IMAGE_TAG

# Load environment variables
ENV_FILE=".env.${ENVIRONMENT}"
if [ -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}📋 Loading environment variables from $ENV_FILE${NC}"
    source $ENV_FILE
else
    echo -e "${YELLOW}⚠️  Warning: $ENV_FILE not found, using system environment variables${NC}"
fi

# Validate required environment variables
REQUIRED_VARS=(
    "FLASK_SECRET_KEY"
    "SUPABASE_URL"
    "SUPABASE_ANON_KEY"
    "STRIPE_SECRET_KEY"
)

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var:-}" ]; then
        echo -e "${RED}❌ Error: Required environment variable $var not set${NC}"
        exit 1
    fi
done

# Deploy to Cloud Run
echo -e "${YELLOW}🚀 Deploying to Cloud Run...${NC}"
gcloud run deploy $SERVICE_NAME \
    --image $IMAGE_TAG \
    --region $REGION \
    --platform managed \
    --allow-unauthenticated \
    --memory 1Gi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 10 \
    --timeout 300 \
    --concurrency 80 \
    --set-env-vars FLASK_SECRET_KEY="$FLASK_SECRET_KEY" \
    --set-env-vars ALLOWED_ORIGINS="${ALLOWED_ORIGINS:-http://localhost:3000,http://localhost:5174}" \
    --set-env-vars SUPABASE_URL="$SUPABASE_URL" \
    --set-env-vars SUPABASE_ANON_KEY="$SUPABASE_ANON_KEY" \
    --set-env-vars SUPABASE_SERVICE_KEY="${SUPABASE_SERVICE_KEY:-$SUPABASE_ANON_KEY}" \
    --set-env-vars STRIPE_SECRET_KEY="$STRIPE_SECRET_KEY" \
    --set-env-vars STRIPE_WEBHOOK_SECRET="${STRIPE_WEBHOOK_SECRET:-}" \
    --set-env-vars RESEND_API_KEY="${RESEND_API_KEY:-}" \
    --set-env-vars WHATSAPP_WEBHOOK_URL="${WHATSAPP_WEBHOOK_URL:-}" \
    --set-env-vars SEED_TOKEN="${SEED_TOKEN:-bluxa-seed-2024}"

# Get service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.url)')

echo ""
echo -e "${GREEN}✅ Deployment successful!${NC}"
echo -e "${GREEN}🌐 Service URL: $SERVICE_URL${NC}"
echo -e "${GREEN}🏥 Health check: $SERVICE_URL/health${NC}"
echo -e "${GREEN}📚 API pricing: $SERVICE_URL/pricing${NC}"
echo ""
echo -e "${BLUE}📋 Next steps:${NC}"
echo "1. Test the health endpoint: curl $SERVICE_URL/health"
echo "2. Set up Stripe webhook: $SERVICE_URL/webhooks/stripe"
echo "3. Create super admin: curl -X POST $SERVICE_URL/seed/super-admin -H 'X-Seed-Token: \$SEED_TOKEN'"
echo "4. Update frontend REACT_APP_API_URL to: $SERVICE_URL"
echo ""
