#!/usr/bin/env bash
set -euo pipefail

# BLuxA Corp - Stripe Webhook Development Helper
# Forward Stripe events to your local API for testing

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

LOCAL_PORT=${1:-5000}
WEBHOOK_ENDPOINT="localhost:$LOCAL_PORT/webhooks/stripe"

echo -e "${BLUE}🎧 BLuxA Corp Stripe Webhook Listener${NC}"
echo -e "${BLUE}Forwarding to: $WEBHOOK_ENDPOINT${NC}"
echo ""

# Check if Stripe CLI is installed
if ! command -v stripe >/dev/null 2>&1; then
    echo -e "${RED}❌ Error: Stripe CLI not found${NC}"
    echo ""
    echo -e "${YELLOW}📥 Install Stripe CLI:${NC}"
    echo "macOS: brew install stripe/stripe-cli/stripe"
    echo "Linux: https://stripe.com/docs/stripe-cli#install"
    echo "Windows: https://github.com/stripe/stripe-cli/releases"
    echo ""
    echo -e "${YELLOW}🔐 Then login:${NC}"
    echo "stripe login"
    exit 1
fi

# Check if logged in to Stripe
if ! stripe config --list | grep -q "test_mode = true\|live_mode = true"; then
    echo -e "${RED}❌ Error: Not logged in to Stripe${NC}"
    echo "Please run: stripe login"
    exit 1
fi

# Check if local server is running
echo -e "${YELLOW}🔍 Checking if local server is running...${NC}"
if ! curl -s "http://localhost:$LOCAL_PORT/health" > /dev/null; then
    echo -e "${RED}❌ Error: Local server not responding on port $LOCAL_PORT${NC}"
    echo ""
    echo -e "${YELLOW}🚀 Start your local server first:${NC}"
    echo "python bluxa-corp-merged-production-backend.py"
    echo ""
    exit 1
fi

echo -e "${GREEN}✅ Local server is running${NC}"
echo ""

# Start listening for webhooks
echo -e "${YELLOW}🎧 Starting Stripe webhook listener...${NC}"
echo -e "${YELLOW}📝 Events: payment_intent.succeeded, payment_intent.payment_failed${NC}"
echo -e "${YELLOW}🔗 Endpoint: $WEBHOOK_ENDPOINT${NC}"
echo ""
echo -e "${BLUE}💡 Tip: Keep this running while testing payments${NC}"
echo -e "${BLUE}🛑 Press Ctrl+C to stop${NC}"
echo ""

# Listen for specific events that BLuxA Corp handles
stripe listen \
    --forward-to $WEBHOOK_ENDPOINT \
    --events payment_intent.succeeded,payment_intent.payment_failed,payment_intent.canceled \
    --skip-verify

echo ""
echo -e "${GREEN}🎧 Webhook listener stopped${NC}"
