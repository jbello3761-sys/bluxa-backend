from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import uuid
from datetime import datetime
import stripe
import requests
import logging
from threading import Thread
import time

# BLuxA Corp API - Version 3.0 (Fresh deployment)
app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure CORS for Vercel frontend
CORS(app, origins=[
    "https://bluxa-corp-nextjs-*.vercel.app",
    "https://bluxa-corp-nextjs.vercel.app", 
    "http://localhost:3000",
    "http://127.0.0.1:3000"
])

# Configure Flask-Limiter with Redis storage (fallback to memory if Redis unavailable)
try:
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        storage_uri="redis://localhost:6379",
        default_limits=["1000 per hour", "100 per minute"]
    )
except Exception as e:
    logger.warning(f"Redis not available, using in-memory storage: {e}")
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["1000 per hour", "100 per minute"]
    )

# Configure Stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

# Sample data storage (in production, use a database)
bookings_db = {}
failed_notifications = []
pricing_data = {
    "executive_sedan": 15000,  # $150.00 in cents
    "luxury_suv": 20000,       # $200.00 in cents
    "premium_van": 25000,      # $250.00 in cents
    "airport_transfer": 12000, # $120.00 in cents
}

def send_notification(notification_data):
    """Send notification with proper error handling"""
    try:
        webhook_url = os.getenv('WHATSAPP_WEBHOOK_URL')
        if not webhook_url or webhook_url == 'your-webhook-url-here':
            logger.warning("WhatsApp webhook URL not configured")
            return False
            
        response = requests.post(
            webhook_url,
            json=notification_data,
            timeout=10,
            headers={'Content-Type': 'application/json'}
        )
        response.raise_for_status()
        logger.info(f"Notification sent successfully: {response.status_code}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send notification: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending notification: {e}")
        return False

def retry_failed_notifications():
    """Retry failed notifications with exponential backoff"""
    while True:
        try:
            if failed_notifications:
                logger.info(f"Retrying {len(failed_notifications)} failed notifications")
                successful_retries = []
                
                for notification in failed_notifications[:]:
                    if send_notification(notification):
                        successful_retries.append(notification)
                        failed_notifications.remove(notification)
                
                if successful_retries:
                    logger.info(f"Successfully retried {len(successful_retries)} notifications")
            
            # Wait 5 minutes before next retry
            time.sleep(300)
            
        except Exception as e:
            logger.error(f"Error in retry_failed_notifications: {e}")
            time.sleep(60)  # Wait 1 minute on error

# Start notification retry thread
notification_thread = Thread(target=retry_failed_notifications, daemon=True)
notification_thread.start()
logger.info("Notification retry scheduler started")

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "BLuxA Corp API",
        "version": "3.0"
    })

@app.route('/pricing', methods=['GET'])
def get_pricing():
    return jsonify({
        "pricing": {
            "executive_sedan": {
                "airport_transfer_rate": 75.0,
                "base_rate": 25.0,
                "minimum_charge": 50.0,
                "per_hour_rate": 65.0
            },
            "luxury_suv": {
                "airport_transfer_rate": 75.0,
                "base_rate": 25.0,
                "minimum_charge": 50.0,
                "per_hour_rate": 65.0
            },
            "sprinter_van": {
                "airport_transfer_rate": 75.0,
                "base_rate": 25.0,
                "minimum_charge": 50.0,
                "per_hour_rate": 65.0
            }
        }
    })

@app.route('/bookings', methods=['POST'])
@limiter.limit("10 per minute")
def create_booking():
    try:
        # Check if request has JSON data
        if not request.is_json:
            return jsonify({"error": "Request must be JSON"}), 400
            
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        # Validate required fields
        required_fields = ['pickup_location', 'dropoff_location', 'pickup_datetime']
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            return jsonify({
                "error": f"Missing required fields: {', '.join(missing_fields)}"
            }), 400
        
        # Generate booking ID and UUID
        booking_id = f"BLX-2025-{str(uuid.uuid4())[:8].upper()}"
        booking_uuid = str(uuid.uuid4())
        
        # Calculate estimated price (simplified)
        vehicle_type = data.get('vehicle_type', 'executive_sedan')
        base_price = pricing_data.get(vehicle_type, 15000)
        estimated_price = base_price
        
        # Create booking record
        booking = {
            "id": booking_uuid,
            "booking_id": booking_id,
            "status": "pending",
            "estimated_price": estimated_price,
            "created_at": datetime.now().isoformat(),
            "pickup_location": data.get('pickup_location'),
            "dropoff_location": data.get('dropoff_location'),
            "pickup_datetime": data.get('pickup_datetime'),
            "vehicle_type": vehicle_type,
            "passenger_count": data.get('passenger_count', 1),
            "special_requests": data.get('special_requests', ''),
            "contact_info": data.get('contact_info', {})
        }
        
        # Store booking
        bookings_db[booking_uuid] = booking
        
        # Send notification (non-blocking)
        notification_data = {
            "type": "new_booking",
            "booking_id": booking_id,
            "pickup_location": booking['pickup_location'],
            "dropoff_location": booking['dropoff_location'],
            "pickup_datetime": booking['pickup_datetime'],
            "vehicle_type": booking['vehicle_type']
        }
        
        if not send_notification(notification_data):
            failed_notifications.append(notification_data)
        
        logger.info(f"Booking created: {booking_id}")
        return jsonify(booking), 201
        
    except Exception as e:
        logger.error(f"Error creating booking: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/bookings/<booking_id>', methods=['GET'])
def get_booking(booking_id):
    if booking_id in bookings_db:
        return jsonify(bookings_db[booking_id])
    return jsonify({"error": "Booking not found"}), 404

@app.route('/payments/create-intent', methods=['POST'])
@limiter.limit("5 per minute")
def create_payment_intent():
    try:
        data = request.get_json()
        booking_id = data.get('booking_id')
        
        if booking_id not in bookings_db:
            return jsonify({"error": "Booking not found"}), 404
        
        booking = bookings_db[booking_id]
        amount = booking['estimated_price']
        
        # Create Stripe payment intent
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency='usd',
            metadata={
                'booking_id': booking_id,
                'booking_uuid': booking['id']
            }
        )
        
        return jsonify({
            "id": intent.id,
            "client_secret": intent.client_secret,
            "amount": amount,
            "currency": intent.currency,
            "status": intent.status
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/payments/confirm', methods=['POST'])
@limiter.limit("5 per minute")
def confirm_payment():
    try:
        data = request.get_json()
        payment_intent_id = data.get('payment_intent_id')
        
        # Retrieve payment intent
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        
        if intent.status == 'succeeded':
            # Update booking status
            booking_id = intent.metadata.get('booking_id')
            if booking_id in bookings_db:
                bookings_db[booking_id]['status'] = 'confirmed'
                bookings_db[booking_id]['payment_intent_id'] = payment_intent_id
        
        return jsonify({
            "status": intent.status,
            "payment_intent_id": payment_intent_id
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/payments/<payment_intent_id>/status', methods=['GET'])
def get_payment_status(payment_intent_id):
    try:
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        return jsonify({
            "status": intent.status,
            "amount": intent.amount,
            "currency": intent.currency
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print(f"Starting BLuxA Corp API on port {port}")
    print(f"PORT environment variable: {os.getenv('PORT')}")
    app.run(host='0.0.0.0', port=port, debug=False)
