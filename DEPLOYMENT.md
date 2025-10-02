# BLuxA Corp Backend - Deployment Guide

## Quick Start

### Option 1: Docker (Recommended)
```bash
# Build and run with Docker Compose
docker-compose up --build

# Or build and run manually
docker build -t bluxa-backend .
docker run -p 5000:5000 --env-file bluxa-backend.env bluxa-backend
```

### Option 2: Direct Python
```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export FLASK_ENV=production
export PORT=5000

# Run the application
python app.py
```

## Environment Variables

Create a `.env` file or set these environment variables:

```bash
# Required
FLASK_ENV=production
PORT=5000
STRIPE_SECRET_KEY=sk_test_your_stripe_key
STRIPE_WEBHOOK_SECRET=whsec_your_webhook_secret

# Optional
WHATSAPP_WEBHOOK_URL=https://your-webhook-url.com
SUPABASE_URL=https://your-supabase-url.supabase.co
SUPABASE_ANON_KEY=your_supabase_anon_key
SUPABASE_SERVICE_KEY=your_supabase_service_key

# Redis (optional, for rate limiting)
REDIS_URL=redis://localhost:6379
```

## Platform-Specific Deployment

### Render.com
1. Connect your GitHub repository
2. Select "Web Service"
3. Use these settings:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn --bind 0.0.0.0:$PORT --workers 4 --timeout 120 app:app`
   - **Environment**: Python 3.11

### Railway
1. Connect your GitHub repository
2. Railway will auto-detect Python
3. Set environment variables in Railway dashboard
4. Deploy automatically

### Heroku
1. Create `Procfile` (already included)
2. Connect GitHub repository
3. Enable automatic deploys
4. Set environment variables in Heroku dashboard

### DigitalOcean App Platform
1. Connect GitHub repository
2. Select "Web Service"
3. Use these settings:
   - **Source Directory**: `/bluxa-backend`
   - **Build Command**: `pip install -r requirements.txt`
   - **Run Command**: `gunicorn --bind 0.0.0.0:$PORT --workers 4 --timeout 120 app:app`

### AWS Elastic Beanstalk
1. Install EB CLI: `pip install awsebcli`
2. Initialize: `eb init`
3. Create environment: `eb create`
4. Deploy: `eb deploy`

### Google Cloud Run
1. Build image: `gcloud builds submit --tag gcr.io/PROJECT-ID/bluxa-backend`
2. Deploy: `gcloud run deploy --image gcr.io/PROJECT-ID/bluxa-backend --platform managed`

## Docker Commands

### Build Image
```bash
docker build -t bluxa-backend .
```

### Run Container
```bash
docker run -p 5000:5000 \
  -e FLASK_ENV=production \
  -e STRIPE_SECRET_KEY=your_key \
  bluxa-backend
```

### Run with Environment File
```bash
docker run -p 5000:5000 --env-file bluxa-backend.env bluxa-backend
```

### Docker Compose
```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## Health Checks

The application includes health check endpoints:

- **Docker Health Check**: Built into Dockerfile
- **HTTP Health Check**: `GET /health`
- **Load Balancer**: Use `/health` endpoint

## Monitoring

### Logs
- Application logs are written to stdout
- Use platform-specific log viewing tools
- Docker: `docker logs container_name`

### Metrics
- Health endpoint: `GET /health`
- Rate limiting status in logs
- Notification retry status in logs

## Troubleshooting

### Common Issues

1. **Port Binding Error**
   ```bash
   # Make sure PORT environment variable is set
   export PORT=5000
   ```

2. **Missing Dependencies**
   ```bash
   # Reinstall requirements
   pip install -r requirements.txt
   ```

3. **Environment Variables**
   ```bash
   # Check if variables are set
   echo $STRIPE_SECRET_KEY
   ```

4. **Docker Build Fails**
   ```bash
   # Check Dockerfile syntax
   docker build --no-cache -t bluxa-backend .
   ```

### Testing Deployment

```bash
# Test health endpoint
curl https://your-app-url.com/health

# Test pricing endpoint
curl https://your-app-url.com/pricing

# Test booking (replace with your URL)
curl -X POST https://your-app-url.com/bookings \
  -H "Content-Type: application/json" \
  -d '{
    "pickup_location": "123 Main St, New York, NY",
    "dropoff_location": "456 Broadway, New York, NY",
    "pickup_datetime": "2025-01-15T10:00:00Z"
  }'
```

## Security Notes

- Never commit `.env` files to version control
- Use environment variables for sensitive data
- Enable HTTPS in production
- Configure CORS properly for your frontend domain
- Use strong, unique API keys

## Performance Optimization

- Use Redis for rate limiting in production
- Configure proper worker processes with Gunicorn
- Enable gzip compression
- Use CDN for static assets
- Monitor memory usage and scale accordingly
