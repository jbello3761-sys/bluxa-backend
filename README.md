# BLuxA Corp Flask Backend
# Simple Flask API for luxury transportation booking

## Features
- Health check endpoint
- Dynamic pricing
- Booking creation and management
- Stripe payment integration
- CORS enabled for frontend integration

## API Endpoints
- GET /health - Health check
- GET /pricing - Get vehicle pricing
- POST /bookings - Create new booking
- GET /bookings/{id} - Get booking by ID
- POST /payments/create-intent - Create Stripe payment intent
- POST /payments/confirm - Confirm payment
- GET /payments/{id}/status - Get payment status

## Environment Variables
Copy env.example to .env and configure:
- STRIPE_SECRET_KEY - Your Stripe secret key
- SUPABASE_URL - Your Supabase project URL
- SUPABASE_SERVICE_KEY - Your Supabase service role key
- PORT - Server port (default: 5000)

## Local Development
```bash
pip install -r requirements.txt
python app.py
```

## Render Deployment
1. Connect your GitHub repository
2. Set environment variables in Render dashboard
3. Deploy as a Web Service