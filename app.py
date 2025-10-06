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
import resend

# BLuxA Corp API - Version 3.0 (Fresh deployment)
app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure CORS for Vercel frontend - Allow all origins for now
CORS(app, origins="*", methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type", "Authorization"])

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

# Configure Resend for emails
resend.api_key = os.getenv('RESEND_API_KEY')

# Email configuration
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@bluxatransportation.com')
DRIVER_EMAIL = os.getenv('DRIVER_EMAIL', 'drivers@bluxatransportation.com')
FROM_EMAIL = os.getenv('FROM_EMAIL', 'bookings@bluxatransportation.com')

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

def send_email(to_email, subject, html_content, text_content=None):
    """Send email using Resend"""
    try:
        if not resend.api_key or resend.api_key == 'your-resend-key-here':
            logger.warning("Resend API key not configured")
            return False
            
        params = {
            "from": FROM_EMAIL,
            "to": [to_email],
            "subject": subject,
            "html": html_content,
        }
        
        if text_content:
            params["text"] = text_content
            
        email = resend.Emails.send(params)
        logger.info(f"Email sent successfully to {to_email}: {email.id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False

def send_booking_confirmation(booking_data):
    """Send booking confirmation emails to customer, admin, and driver"""
    try:
        # Format booking details
        pickup_datetime = datetime.fromisoformat(booking_data['pickup_datetime'].replace('Z', '+00:00'))
        formatted_datetime = pickup_datetime.strftime('%A, %B %d, %Y at %I:%M %p')
        amount_dollars = booking_data['estimated_price'] / 100
        
        # Customer confirmation email
        customer_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #2563eb 0%, #dc2626 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9fafb; padding: 30px; border-radius: 0 0 10px 10px; }}
                .booking-details {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                .detail-row {{ display: flex; justify-content: space-between; margin: 10px 0; padding: 10px 0; border-bottom: 1px solid #e5e7eb; }}
                .detail-label {{ font-weight: bold; color: #6b7280; }}
                .detail-value {{ color: #111827; }}
                .total {{ background: #2563eb; color: white; padding: 15px; border-radius: 8px; text-align: center; font-size: 18px; font-weight: bold; margin: 20px 0; }}
                .footer {{ text-align: center; color: #6b7280; font-size: 14px; margin-top: 30px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>BLuxA Transportation</h1>
                    <h2>Booking Confirmation</h2>
                </div>
                <div class="content">
                    <p>Dear {booking_data['contact_info']['name']},</p>
                    <p>Thank you for choosing BLuxA Transportation! Your booking has been confirmed.</p>
                    
                    <div class="booking-details">
                        <h3>Booking Details</h3>
                        <div class="detail-row">
                            <span class="detail-label">Booking Code:</span>
                            <span class="detail-value">{booking_data['booking_id']}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Pickup Location:</span>
                            <span class="detail-value">{booking_data['pickup_location']}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Destination:</span>
                            <span class="detail-value">{booking_data['dropoff_location']}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Pickup Date & Time:</span>
                            <span class="detail-value">{formatted_datetime}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Vehicle Type:</span>
                            <span class="detail-value">{booking_data['vehicle_type'].replace('_', ' ').title()}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Passengers:</span>
                            <span class="detail-value">{booking_data['passenger_count']}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Status:</span>
                            <span class="detail-value">{booking_data['status'].title()}</span>
                        </div>
                    </div>
                    
                    <div class="total">
                        Total Amount: ${amount_dollars:.2f}
                    </div>
                    
                    <p>Your driver will contact you 15 minutes before pickup. If you have any questions, please contact us at +1 (555) 123-4567.</p>
                    
                    <div class="footer">
                        <p>BLuxA Transportation - Premium Luxury Transportation</p>
                        <p>New York City, NY | 24/7 Available</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Admin notification email
        admin_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #dc2626; color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9fafb; padding: 30px; border-radius: 0 0 10px 10px; }}
                .booking-details {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                .detail-row {{ display: flex; justify-content: space-between; margin: 10px 0; padding: 10px 0; border-bottom: 1px solid #e5e7eb; }}
                .detail-label {{ font-weight: bold; color: #6b7280; }}
                .detail-value {{ color: #111827; }}
                .urgent {{ background: #fef2f2; border: 1px solid #fecaca; padding: 15px; border-radius: 8px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>New Booking Alert</h1>
                    <h2>BLuxA Transportation</h2>
                </div>
                <div class="content">
                    <div class="urgent">
                        <h3>🚨 New Booking Requires Attention</h3>
                        <p>A new booking has been created and requires driver assignment.</p>
                    </div>
                    
                    <div class="booking-details">
                        <h3>Booking Information</h3>
                        <div class="detail-row">
                            <span class="detail-label">Booking Code:</span>
                            <span class="detail-value">{booking_data['booking_id']}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Customer:</span>
                            <span class="detail-value">{booking_data['contact_info']['name']}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Email:</span>
                            <span class="detail-value">{booking_data['contact_info']['email']}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Phone:</span>
                            <span class="detail-value">{booking_data['contact_info']['phone']}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Pickup:</span>
                            <span class="detail-value">{booking_data['pickup_location']}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Destination:</span>
                            <span class="detail-value">{booking_data['dropoff_location']}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Date & Time:</span>
                            <span class="detail-value">{formatted_datetime}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Vehicle:</span>
                            <span class="detail-value">{booking_data['vehicle_type'].replace('_', ' ').title()}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Amount:</span>
                            <span class="detail-value">${amount_dollars:.2f}</span>
                        </div>
                    </div>
                    
                    <p><strong>Action Required:</strong> Please assign a driver and confirm the booking.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Driver notification email
        driver_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #059669; color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9fafb; padding: 30px; border-radius: 0 0 10px 10px; }}
                .booking-details {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                .detail-row {{ display: flex; justify-content: space-between; margin: 10px 0; padding: 10px 0; border-bottom: 1px solid #e5e7eb; }}
                .detail-label {{ font-weight: bold; color: #6b7280; }}
                .detail-value {{ color: #111827; }}
                .instructions {{ background: #ecfdf5; border: 1px solid #a7f3d0; padding: 15px; border-radius: 8px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>New Assignment</h1>
                    <h2>BLuxA Transportation</h2>
                </div>
                <div class="content">
                    <div class="instructions">
                        <h3>📋 Driver Instructions</h3>
                        <p>You have been assigned a new booking. Please review the details below and contact the customer 15 minutes before pickup.</p>
                    </div>
                    
                    <div class="booking-details">
                        <h3>Trip Details</h3>
                        <div class="detail-row">
                            <span class="detail-label">Booking Code:</span>
                            <span class="detail-value">{booking_data['booking_id']}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Customer Name:</span>
                            <span class="detail-value">{booking_data['contact_info']['name']}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Customer Phone:</span>
                            <span class="detail-value">{booking_data['contact_info']['phone']}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Pickup Location:</span>
                            <span class="detail-value">{booking_data['pickup_location']}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Destination:</span>
                            <span class="detail-value">{booking_data['dropoff_location']}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Pickup Time:</span>
                            <span class="detail-value">{formatted_datetime}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Vehicle Type:</span>
                            <span class="detail-value">{booking_data['vehicle_type'].replace('_', ' ').title()}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Passengers:</span>
                            <span class="detail-value">{booking_data['passenger_count']}</span>
                        </div>
                    </div>
                    
                    <p><strong>Important:</strong> Please arrive 5 minutes early and contact the customer upon arrival.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Send emails asynchronously
        def send_emails():
            # Send to customer
            send_email(
                booking_data['contact_info']['email'],
                f"Booking Confirmation - {booking_data['booking_id']}",
                customer_html
            )
            
            # Send to admin
            send_email(
                ADMIN_EMAIL,
                f"New Booking Alert - {booking_data['booking_id']}",
                admin_html
            )
            
            # Send to driver
            send_email(
                DRIVER_EMAIL,
                f"New Assignment - {booking_data['booking_id']}",
                driver_html
            )
        
        # Run email sending in background thread
        email_thread = Thread(target=send_emails)
        email_thread.daemon = True
        email_thread.start()
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to send booking confirmation emails: {e}")
        return False

def send_payment_receipt(booking_data, payment_intent_id):
    """Send payment receipt emails to customer and admin"""
    try:
        # Format booking details
        pickup_datetime = datetime.fromisoformat(booking_data['pickup_datetime'].replace('Z', '+00:00'))
        formatted_datetime = pickup_datetime.strftime('%A, %B %d, %Y at %I:%M %p')
        amount_dollars = booking_data['estimated_price'] / 100
        
        # Customer receipt email
        customer_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #059669 0%, #2563eb 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9fafb; padding: 30px; border-radius: 0 0 10px 10px; }}
                .receipt-details {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                .detail-row {{ display: flex; justify-content: space-between; margin: 10px 0; padding: 10px 0; border-bottom: 1px solid #e5e7eb; }}
                .detail-label {{ font-weight: bold; color: #6b7280; }}
                .detail-value {{ color: #111827; }}
                .total {{ background: #059669; color: white; padding: 15px; border-radius: 8px; text-align: center; font-size: 18px; font-weight: bold; margin: 20px 0; }}
                .payment-info {{ background: #ecfdf5; border: 1px solid #a7f3d0; padding: 15px; border-radius: 8px; margin: 20px 0; }}
                .footer {{ text-align: center; color: #6b7280; font-size: 14px; margin-top: 30px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>BLuxA Transportation</h1>
                    <h2>Payment Receipt</h2>
                </div>
                <div class="content">
                    <p>Dear {booking_data['contact_info']['name']},</p>
                    <p>Thank you for your payment! Your booking is now confirmed and paid.</p>
                    
                    <div class="payment-info">
                        <h3>✅ Payment Confirmed</h3>
                        <p>Payment ID: {payment_intent_id}</p>
                        <p>Status: Paid</p>
                    </div>
                    
                    <div class="receipt-details">
                        <h3>Booking Details</h3>
                        <div class="detail-row">
                            <span class="detail-label">Booking Code:</span>
                            <span class="detail-value">{booking_data['booking_id']}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Pickup Location:</span>
                            <span class="detail-value">{booking_data['pickup_location']}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Destination:</span>
                            <span class="detail-value">{booking_data['dropoff_location']}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Pickup Date & Time:</span>
                            <span class="detail-value">{formatted_datetime}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Vehicle Type:</span>
                            <span class="detail-value">{booking_data['vehicle_type'].replace('_', ' ').title()}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Passengers:</span>
                            <span class="detail-value">{booking_data['passenger_count']}</span>
                        </div>
                    </div>
                    
                    <div class="total">
                        Amount Paid: ${amount_dollars:.2f}
                    </div>
                    
                    <p>Your driver will contact you 15 minutes before pickup. If you have any questions, please contact us at +1 (555) 123-4567.</p>
                    
                    <div class="footer">
                        <p>BLuxA Transportation - Premium Luxury Transportation</p>
                        <p>New York City, NY | 24/7 Available</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Admin payment notification email
        admin_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #059669; color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9fafb; padding: 30px; border-radius: 0 0 10px 10px; }}
                .receipt-details {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                .detail-row {{ display: flex; justify-content: space-between; margin: 10px 0; padding: 10px 0; border-bottom: 1px solid #e5e7eb; }}
                .detail-label {{ font-weight: bold; color: #6b7280; }}
                .detail-value {{ color: #111827; }}
                .payment-confirmed {{ background: #ecfdf5; border: 1px solid #a7f3d0; padding: 15px; border-radius: 8px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Payment Received</h1>
                    <h2>BLuxA Transportation</h2>
                </div>
                <div class="content">
                    <div class="payment-confirmed">
                        <h3>💰 Payment Confirmed</h3>
                        <p>A customer has successfully paid for their booking.</p>
                    </div>
                    
                    <div class="receipt-details">
                        <h3>Payment Details</h3>
                        <div class="detail-row">
                            <span class="detail-label">Payment ID:</span>
                            <span class="detail-value">{payment_intent_id}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Booking Code:</span>
                            <span class="detail-value">{booking_data['booking_id']}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Customer:</span>
                            <span class="detail-value">{booking_data['contact_info']['name']}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Email:</span>
                            <span class="detail-value">{booking_data['contact_info']['email']}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Phone:</span>
                            <span class="detail-value">{booking_data['contact_info']['phone']}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Pickup:</span>
                            <span class="detail-value">{booking_data['pickup_location']}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Destination:</span>
                            <span class="detail-value">{booking_data['dropoff_location']}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Date & Time:</span>
                            <span class="detail-value">{formatted_datetime}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Amount:</span>
                            <span class="detail-value">${amount_dollars:.2f}</span>
                        </div>
                    </div>
                    
                    <p><strong>Action Required:</strong> Please ensure driver assignment and confirm pickup details.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Send emails asynchronously
        def send_receipt_emails():
            # Send to customer
            send_email(
                booking_data['contact_info']['email'],
                f"Payment Receipt - {booking_data['booking_id']}",
                customer_html
            )
            
            # Send to admin
            send_email(
                ADMIN_EMAIL,
                f"Payment Received - {booking_data['booking_id']}",
                admin_html
            )
        
        # Run email sending in background thread
        email_thread = Thread(target=send_receipt_emails)
        email_thread.daemon = True
        email_thread.start()
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to send payment receipt emails: {e}")
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
                "airport_transfer_rate": 7500,  # $75.00 in cents
                "base_rate": 2500,  # $25.00 in cents
                "minimum_charge": 5000,  # $50.00 in cents
                "per_hour_rate": 6500   # $65.00 in cents
            },
            "luxury_suv": {
                "airport_transfer_rate": 10500,  # $105.00 in cents
                "base_rate": 3500,  # $35.00 in cents
                "minimum_charge": 7000,  # $70.00 in cents
                "per_hour_rate": 9500   # $95.00 in cents
            },
            "sprinter_van": {
                "airport_transfer_rate": 15000,  # $150.00 in cents
                "base_rate": 5000,  # $50.00 in cents
                "minimum_charge": 10000,  # $100.00 in cents
                "per_hour_rate": 12000   # $120.00 in cents
            },
            "stretch_limo": {
                "airport_transfer_rate": 18000,  # $180.00 in cents
                "base_rate": 6000,  # $60.00 in cents
                "minimum_charge": 12000,  # $120.00 in cents
                "per_hour_rate": 15000   # $150.00 in cents
            }
        },
        "currency": "USD"
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
        
        # Send booking confirmation emails (non-blocking)
        try:
            send_booking_confirmation(booking)
            logger.info(f"Booking confirmation emails sent for {booking_id}")
        except Exception as e:
            logger.error(f"Failed to send booking confirmation emails: {e}")
        
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
        # Check if request has JSON data
        if not request.is_json:
            return jsonify({"error": "Request must be JSON"}), 400
            
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        booking_id = data.get('booking_id')
        if not booking_id:
            return jsonify({"error": "booking_id is required"}), 400
        
        if booking_id not in bookings_db:
            return jsonify({"error": "Booking not found"}), 404
        
        booking = bookings_db[booking_id]
        amount = booking['estimated_price']
        
        # Validate Stripe API key
        if not stripe.api_key:
            return jsonify({"error": "Stripe API key not configured"}), 500
        
        # Create Stripe payment intent
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency='usd',
            metadata={
                'booking_id': booking_id,
                'booking_uuid': booking['id']
            }
        )
        
        logger.info(f"Created payment intent {intent.id} for booking {booking_id}")
        
        return jsonify({
            "id": intent.id,
            "client_secret": intent.client_secret,
            "amount": amount,
            "currency": intent.currency,
            "status": intent.status
        })
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error: {e}")
        return jsonify({"error": f"Payment processing error: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

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
                
                # Send payment receipt emails (non-blocking)
                try:
                    send_payment_receipt(bookings_db[booking_id], payment_intent_id)
                    logger.info(f"Payment receipt emails sent for {booking_id}")
                except Exception as e:
                    logger.error(f"Failed to send payment receipt emails: {e}")
        
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
