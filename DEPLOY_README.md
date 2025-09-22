# BLuxA Corp - Production Deployment Guide

Complete deployment infrastructure for the BLuxA Corp Transportation Management System API.

## 📁 Files Overview

- **`bluxa_openapi.yaml`** — Complete OpenAPI 3.0 specification
- **`.env.example`** — Backend environment variables template
- **`.env.frontend.example`** — Frontend environment variables template
- **`Dockerfile`** — Production-ready container configuration
- **`requirements.txt`** — Python dependencies with security updates
- **`.github/workflows/deploy-cloudrun.yml`** — CI/CD pipeline for Google Cloud Run
- **`scripts/deploy_cloudrun.sh`** — Manual deployment script
- **`scripts/stripe_listen.sh`** — Local webhook testing helper

## 🚀 Quick Start (Google Cloud Run)

### 1. Prerequisites

- Google Cloud Project with billing enabled
- GitHub repository with the code
- Stripe account (test/live keys)
- Supabase project
- Resend account (for emails)
- Make.com account (for WhatsApp)

### 2. Set GitHub Secrets

In your GitHub repository settings → Secrets and variables → Actions, add:

**Required Secrets:**
```
GCP_PROJECT_ID=your-gcp-project-id
GCP_WORKLOAD_IDENTITY_PROVIDER=projects/123456789/locations/global/workloadIdentityPools/github/providers/github
GCP_SERVICE_ACCOUNT_EMAIL=github-actions@your-project.iam.gserviceaccount.com
FLASK_SECRET_KEY=your-super-secret-flask-key-here
ALLOWED_ORIGINS=https://your-frontend-domain.com,https://your-vercel-app.vercel.app
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-supabase-anon-key
SUPABASE_SERVICE_KEY=your-supabase-service-role-key
STRIPE_SECRET_KEY=sk_live_your-stripe-secret-key
STRIPE_WEBHOOK_SECRET=whsec_your-webhook-signing-secret
RESEND_API_KEY=re_your-resend-api-key
WHATSAPP_WEBHOOK_URL=https://hook.make.com/your-webhook-url
SEED_TOKEN=your-super-admin-seed-token
```

### 3. Deploy

1. **Push to main branch** → GitHub Actions automatically builds and deploys
2. **Get service URL** from GitHub Actions logs or Google Cloud Console
3. **Set up Stripe webhook** in Stripe Dashboard:
   - Endpoint: `https://your-cloud-run-url/webhooks/stripe`
   - Events: `payment_intent.succeeded`, `payment_intent.payment_failed`
   - Copy webhook signing secret to `STRIPE_WEBHOOK_SECRET`

### 4. Initialize System

```bash
# Create super admin (one-time setup)
curl -X POST https://your-cloud-run-url/seed/super-admin \
  -H "X-Seed-Token: your-seed-token"

# Test health endpoint
curl https://your-cloud-run-url/health

# Test pricing endpoint
curl https://your-cloud-run-url/pricing
```

## 🛠️ Local Development

### 1. Setup Environment

```bash
# Clone repository
git clone https://github.com/your-org/bluxa-corp-api.git
cd bluxa-corp-api

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env.development
# Edit .env.development with your local values
```

### 2. Run Local Server

```bash
# Load environment variables
export $(cat .env.development | xargs)

# Start Flask server
python bluxa-corp-merged-production-backend.py
```

### 3. Test Stripe Webhooks Locally

```bash
# In a separate terminal
./scripts/stripe_listen.sh

# This will:
# - Check if Stripe CLI is installed
# - Verify local server is running
# - Forward webhooks to localhost:5000/webhooks/stripe
```

## 🔧 Manual Deployment

For manual deployments or custom configurations:

```bash
# Make script executable
chmod +x scripts/deploy_cloudrun.sh

# Set environment variables
export GCP_PROJECT_ID=your-project-id
export GCP_REGION=us-east4

# Deploy
./scripts/deploy_cloudrun.sh production
```

## 🏗️ Architecture

### Container Configuration
- **Base Image:** Python 3.11 slim
- **Security:** Non-root user, minimal attack surface
- **Health Check:** Built-in endpoint monitoring
- **Resource Limits:** 1 CPU, 1GB RAM, 80 concurrent requests

### Database Schema
- **Supabase PostgreSQL** with Row Level Security
- **Tables:** users, drivers, vehicles, bookings, payments, admin_users, system_settings, audit_logs, notifications, ratings, vehicle_assignments
- **Authentication:** Supabase Auth with JWT tokens

### External Integrations
- **Stripe:** Payment processing with webhooks
- **Resend:** Transactional email delivery
- **Make.com/Twilio:** WhatsApp notifications
- **Google Maps:** Address autocomplete (frontend)

## 🔒 Security Features

### Authentication & Authorization
- **JWT tokens** via Supabase Auth
- **Role-based access control** (customer, driver, admin)
- **Row Level Security** in database
- **API rate limiting** with Flask-Limiter

### Data Protection
- **CORS restrictions** to specific origins
- **Input validation** and sanitization
- **Audit logging** for all sensitive operations
- **Encrypted environment variables**

### Production Hardening
- **Non-root container user**
- **Minimal base image**
- **Health checks** and monitoring
- **Automatic retries** for failed operations

## 📊 Monitoring & Logging

### Health Checks
- **`/health`** endpoint for service status
- **Database connectivity** verification
- **External service** availability checks

### Audit Logging
- **User actions** (login, registration, bookings)
- **Admin operations** (driver assignment, vehicle management)
- **Payment events** (successful/failed transactions)
- **System changes** (settings updates, status changes)

### Error Handling
- **Comprehensive try-catch** blocks
- **Structured logging** with context
- **Graceful degradation** for external service failures
- **Automatic retry logic** for transient failures

## 🔄 CI/CD Pipeline

### GitHub Actions Workflow
1. **Code checkout** and Python setup
2. **Dependency installation** and basic tests
3. **Docker image build** and push to GCR
4. **Cloud Run deployment** with environment variables
5. **Service URL output** and health check

### Deployment Stages
- **Test:** Import validation and basic health checks
- **Build:** Docker containerization with security scanning
- **Deploy:** Zero-downtime deployment to Cloud Run
- **Verify:** Automated health check and service validation

## 🌐 Frontend Integration

### Environment Variables
```javascript
// React .env.local
REACT_APP_API_URL=https://your-cloud-run-url
REACT_APP_STRIPE_PUBLISHABLE_KEY=pk_live_your-key
REACT_APP_SUPABASE_URL=https://your-project.supabase.co
REACT_APP_SUPABASE_ANON_KEY=your-anon-key
```

### API Usage
```javascript
// Booking creation
const booking = await fetch(`${API_URL}/bookings`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(bookingData)
});

// Payment processing (use booking.id UUID, not booking_id)
const paymentIntent = await fetch(`${API_URL}/payments/create-intent`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ booking_id: booking.id })
});
```

## 🆘 Troubleshooting

### Common Issues

**1. Deployment Fails**
```bash
# Check GitHub Actions logs
# Verify all secrets are set correctly
# Ensure GCP permissions are configured
```

**2. Stripe Webhooks Not Working**
```bash
# Verify webhook URL in Stripe Dashboard
# Check STRIPE_WEBHOOK_SECRET matches
# Test with stripe CLI: stripe listen --forward-to your-url/webhooks/stripe
```

**3. Database Connection Issues**
```bash
# Verify Supabase URL and keys
# Check Row Level Security policies
# Ensure service role key has proper permissions
```

**4. Email/SMS Not Sending**
```bash
# Check Resend API key validity
# Verify WhatsApp webhook URL
# Review notification retry logs in admin panel
```

### Debug Commands
```bash
# Check service logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=bluxa-api" --limit 50

# Test endpoints
curl -H "Authorization: Bearer $JWT_TOKEN" https://your-url/admin/dashboard

# Retry failed notifications
curl -X POST https://your-url/admin/notifications/retry -H "Authorization: Bearer $ADMIN_TOKEN"
```

## 📞 Support

For deployment issues or questions:
- **API Documentation:** `https://your-cloud-run-url/docs` (if implemented)
- **Health Status:** `https://your-cloud-run-url/health`
- **GitHub Issues:** Create issue in repository
- **Email:** api@bluxacorp.com

---

**🎉 Your BLuxA Corp API is now production-ready!**
