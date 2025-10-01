from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import uuid
from datetime import datetime
import stripe
import json

app = Flask(__name__)
CORS(app)

# Configure Stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

# Sample data storage (in production, use a database)
bookings_db = {}
pricing_data = {
    "executive_sedan": 15000,  # $150.00 in cents
    "luxury_suv": 20000,       # $200.00 in cents
    "premium_van": 25000,      # $250.00 in cents
    "airport_transfer": 12000, # $120.00 in cents
}

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "BLuxA Corp API"
    })

@app.route('/pricing', methods=['GET'])
def get_pricing():
    return jsonify({
        "vehicle_types": pricing_data,
        "currency": "USD",
        "unit": "cents"
    })

@app.route('/bookings', methods=['POST'])
def create_booking():
    try:
        data = request.get_json()
        
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
            **data
        }
        
        # Store booking
        bookings_db[booking_uuid] = booking
        
        return jsonify(booking), 201
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/bookings/<booking_id>', methods=['GET'])
def get_booking(booking_id):
    if booking_id in bookings_db:
        return jsonify(bookings_db[booking_id])
    return jsonify({"error": "Booking not found"}), 404

@app.route('/payments/create-intent', methods=['POST'])
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
    app.run(host='0.0.0.0', port=port, debug=False)