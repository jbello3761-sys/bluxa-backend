"""
BLuxA Corp Transportation Management System - Merged Production Backend
Complete with all patch improvements and enhancements integrated
"""

import os
import json
import uuid
import hashlib
import hmac
import time
from datetime import datetime, timedelta, date, time as time_type
from decimal import Decimal
from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import stripe
from supabase import create_client, Client
import requests
from typing import Dict, List, Optional
import logging
from functools import wraps
import threading

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'bluxa-corp-secret-key-2024')

# Enhanced CORS configuration with environment-based security
ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000,http://localhost:5174').split(',')
CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=True)

# Rate limiting for security
limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Environment variables
SUPABASE_URL = os.getenv('SUPABASE_URL', '')
SUPABASE_ANON_KEY = os.getenv('SUPABASE_ANON_KEY', '')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY', '')
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY', '')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', '')
RESEND_API_KEY = os.getenv('RESEND_API_KEY', '')
WHATSAPP_WEBHOOK_URL = os.getenv('WHATSAPP_WEBHOOK_URL', '')

# Initialize services
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY) if SUPABASE_URL and SUPABASE_ANON_KEY else None
stripe.api_key = STRIPE_SECRET_KEY

# Authentication decorator with strict role checking
def auth_required(roles=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            auth_header = request.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Bearer '):
                return jsonify({'error': 'Authentication required'}), 401
            
            token = auth_header.split(' ')[1]
            
            try:
                # Verify JWT token with Supabase Auth (source of truth)
                user_response = supabase.auth.get_user(token)
                if not user_response.user:
                    return jsonify({'error': 'Invalid token'}), 401
                
                user = user_response.user
                user_role = user.user_metadata.get('role', 'customer')
                
                # Strict role checking for admin endpoints
                if roles and user_role not in roles:
                    logger.warning(f"Access denied: User {user.id} with role {user_role} attempted to access {request.endpoint}")
                    return jsonify({'error': 'Insufficient permissions'}), 403
                
                # Add user info to request context
                request.user = user
                request.user_role = user_role
                
                return f(*args, **kwargs)
            except Exception as e:
                logger.error(f"Authentication error: {str(e)}")
                return jsonify({'error': 'Authentication failed'}), 401
        
        return decorated_function
    return decorator

# Utility functions with consistent ID formats
def generate_booking_id():
    """Generate unique booking ID in BLX format"""
    timestamp = datetime.now().strftime('%Y%m%d')
    random_part = str(uuid.uuid4())[:6].upper()
    return f"BLX{timestamp}{random_part}"

def generate_payment_id():
    """Generate unique payment ID in PAY format"""
    timestamp = datetime.now().strftime('%Y%m%d')
    random_part = str(uuid.uuid4())[:6].upper()
    return f"PAY{timestamp}{random_part}"

def generate_driver_id():
    """Generate unique driver ID in DRV format"""
    result = supabase.table('drivers').select('driver_id').order('created_at', desc=True).limit(1).execute()
    if result.data:
        last_id = result.data[0]['driver_id']
        number = int(last_id[3:]) + 1
    else:
        number = 1
    return f"DRV{number:03d}"

def generate_vehicle_id():
    """Generate unique vehicle ID in VEH format"""
    result = supabase.table('vehicles').select('vehicle_id').order('created_at', desc=True).limit(1).execute()
    if result.data:
        last_id = result.data[0]['vehicle_id']
        number = int(last_id[3:]) + 1
    else:
        number = 1
    return f"VEH{number:03d}"

def get_pricing_from_db(vehicle_type: str) -> Dict:
    """
    Get pricing from DB with proper minimum handling (PATCHED VERSION).
    Priority:
      1) vehicles table (per vehicle_type, status 'available')
      2) system_settings (vehicle_type_base_rate, _hourly_rate, _airport_rate)
      3) hardcoded defaults
    """
    try:
        # 1) Vehicles table (preferred source)
        vehicle_result = supabase.table('vehicles').select(
            'base_rate, per_hour_rate, airport_surcharge, minimum_charge'
        ).eq('vehicle_type', vehicle_type).eq('status', 'available').limit(1).execute()

        if vehicle_result.data:
            v = vehicle_result.data[0]
            base_rate = float(v['base_rate'])
            per_hour_rate = float(v['per_hour_rate'])
            airport_surcharge = float(v.get('airport_surcharge', 10.00))
            # Respect explicit minimum_charge if present, else 2x base_rate
            minimum_charge = float(v['minimum_charge']) if v.get('minimum_charge') is not None else base_rate * 2
            return {
                'base_rate': base_rate,
                'per_hour_rate': per_hour_rate,
                'airport_transfer_rate': per_hour_rate + airport_surcharge,
                'minimum_charge': minimum_charge
            }

        # 2) system_settings fallback
        keys = [f'{vehicle_type}_base_rate', f'{vehicle_type}_hourly_rate', f'{vehicle_type}_airport_rate']
        settings = supabase.table('system_settings').select('setting_key, setting_value').in_('setting_key', keys).execute()

        if settings.data:
            m = {s['setting_key']: float(s['setting_value']) for s in settings.data}
            base_rate = m.get(f'{vehicle_type}_base_rate', 25.00)
            hourly_rate = m.get(f'{vehicle_type}_hourly_rate', 65.00)
            airport_rate = m.get(f'{vehicle_type}_airport_rate', hourly_rate + 10.00)
            minimum_charge = base_rate * 2  # no explicit min in settings; use heuristic
            return {
                'base_rate': base_rate,
                'per_hour_rate': hourly_rate,
                'airport_transfer_rate': airport_rate,
                'minimum_charge': minimum_charge
            }

        # 3) hardcoded defaults
        defaults = {
            'executive_sedan': {'base_rate': 25.00, 'per_hour_rate': 65.00},
            'luxury_suv': {'base_rate': 35.00, 'per_hour_rate': 95.00},
            'sprinter_van': {'base_rate': 45.00, 'per_hour_rate': 120.00}
        }
        d = defaults.get(vehicle_type, defaults['executive_sedan'])
        return {
            'base_rate': d['base_rate'],
            'per_hour_rate': d['per_hour_rate'],
            'airport_transfer_rate': d['per_hour_rate'] + 10.00,
            'minimum_charge': d['base_rate'] * 2
        }

    except Exception as e:
        # last‑ditch fallback
        return {
            'base_rate': 25.00,
            'per_hour_rate': 65.00,
            'airport_transfer_rate': 75.00,
            'minimum_charge': 50.00
        }

def calculate_price(vehicle_type: str, duration_minutes: int, is_airport_transfer: bool = False) -> float:
    """Calculate booking price based on vehicle type and duration using database pricing"""
    config = get_pricing_from_db(vehicle_type)
    
    if is_airport_transfer:
        price = config['airport_transfer_rate']
    else:
        hours = duration_minutes / 60.0
        price = config['base_rate'] + (config['per_hour_rate'] * hours)
    
    return max(price, config['minimum_charge'])

def create_audit_log(user_id: str, user_type: str, action: str, resource_type: str = None, 
                    resource_id: str = None, details: dict = None):
    """Create audit log entry for all key events"""
    try:
        audit_data = {
            'user_id': user_id,
            'user_type': user_type,
            'action': action,
            'resource_type': resource_type,
            'resource_id': resource_id,
            'details': details or {},
            'ip_address': request.remote_addr,
            'user_agent': request.headers.get('User-Agent', '')
        }
        supabase.table('audit_logs').insert(audit_data).execute()
        logger.info(f"Audit log created: {action} by {user_type} {user_id}")
    except Exception as e:
        logger.error(f"Failed to create audit log: {str(e)}")

def create_notification(recipient_id: str, recipient_type: str, notification_type: str, 
                       title: str, message: str, metadata: dict = None):
    """Create notification entry with retry support"""
    try:
        notification_data = {
            'recipient_id': recipient_id,
            'recipient_type': recipient_type,
            'type': notification_type,
            'title': title,
            'message': message,
            'metadata': metadata or {},
            'status': 'pending',
            'retry_count': 0,
            'max_retries': 3
        }
        result = supabase.table('notifications').insert(notification_data).execute()
        logger.info(f"Notification created: {notification_type} for {recipient_type} {recipient_id}")
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Failed to create notification: {str(e)}")
        return None

def send_email_with_retry(to_email: str, subject: str, html_content: str, notification_id: str = None, max_retries: int = 3):
    """Send email using Resend API with retry logic and status tracking"""
    if not RESEND_API_KEY:
        logger.warning("Resend API key not configured")
        if notification_id:
            supabase.table('notifications').update({
                'status': 'failed', 
                'sent_at': datetime.now().isoformat(),
                'error_message': 'Resend API key not configured'
            }).eq('id', notification_id).execute()
        return False
    
    for attempt in range(max_retries):
        try:
            response = requests.post(
                'https://api.resend.com/emails',
                headers={
                    'Authorization': f'Bearer {RESEND_API_KEY}',
                    'Content-Type': 'application/json'
                },
                json={
                    'from': 'BLuxA Corp <noreply@bluxacorp.com>',
                    'to': [to_email],
                    'subject': subject,
                    'html': html_content
                },
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info(f"Email sent successfully to {to_email}")
                if notification_id:
                    supabase.table('notifications').update({
                        'status': 'sent',
                        'email_sent': True,
                        'sent_at': datetime.now().isoformat()
                    }).eq('id', notification_id).execute()
                return True
            else:
                logger.warning(f"Email send attempt {attempt + 1} failed: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.error(f"Email send attempt {attempt + 1} error: {str(e)}")
        
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)  # Exponential backoff
    
    # All attempts failed - update notification with retry count
    logger.error(f"Failed to send email to {to_email} after {max_retries} attempts")
    if notification_id:
        supabase.table('notifications').update({
            'status': 'failed',
            'retry_count': max_retries,
            'sent_at': datetime.now().isoformat(),
            'error_message': f'Failed after {max_retries} attempts'
        }).eq('id', notification_id).execute()
    return False

def send_whatsapp_with_retry(phone: str, message: str, notification_id: str = None, max_retries: int = 3):
    """Send WhatsApp message via webhook with retry logic and status tracking"""
    if not WHATSAPP_WEBHOOK_URL:
        logger.warning("WhatsApp webhook URL not configured")
        if notification_id:
            supabase.table('notifications').update({
                'status': 'failed', 
                'sent_at': datetime.now().isoformat(),
                'error_message': 'WhatsApp webhook URL not configured'
            }).eq('id', notification_id).execute()
        return False
    
    for attempt in range(max_retries):
        try:
            response = requests.post(
                WHATSAPP_WEBHOOK_URL,
                json={
                    'phone': phone,
                    'message': message
                },
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info(f"WhatsApp sent successfully to {phone}")
                if notification_id:
                    supabase.table('notifications').update({
                        'status': 'sent',
                        'sms_sent': True,
                        'sent_at': datetime.now().isoformat()
                    }).eq('id', notification_id).execute()
                return True
            else:
                logger.warning(f"WhatsApp send attempt {attempt + 1} failed: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.error(f"WhatsApp send attempt {attempt + 1} error: {str(e)}")
        
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)  # Exponential backoff
    
    # All attempts failed - update notification with retry count
    logger.error(f"Failed to send WhatsApp to {phone} after {max_retries} attempts")
    if notification_id:
        supabase.table('notifications').update({
            'status': 'failed',
            'retry_count': max_retries,
            'sent_at': datetime.now().isoformat(),
            'error_message': f'Failed after {max_retries} attempts'
        }).eq('id', notification_id).execute()
    return False

def retry_failed_notifications():
    """Background function to retry failed notifications"""
    try:
        # Get failed notifications that haven't exceeded max retries
        failed_notifications = supabase.table('notifications').select('*').eq('status', 'failed').lt('retry_count', 'max_retries').execute()
        
        for notification in failed_notifications.data:
            notification_id = notification['id']
            retry_count = notification['retry_count']
            
            # Update retry count
            supabase.table('notifications').update({
                'retry_count': retry_count + 1,
                'status': 'pending'
            }).eq('id', notification_id).execute()
            
            # Retry sending based on notification type
            if notification['type'] in ['booking_confirmation', 'payment_confirmation', 'driver_assigned']:
                if notification.get('email_sent') is False:
                    # Retry email
                    recipient_email = notification['recipient_id']
                    send_email_with_retry(recipient_email, notification['title'], notification['message'], notification_id)
                
                if notification.get('sms_sent') is False and notification['metadata'].get('phone'):
                    # Retry WhatsApp
                    phone = notification['metadata']['phone']
                    send_whatsapp_with_retry(phone, notification['message'], notification_id)
            
            time.sleep(1)  # Rate limit retries
            
    except Exception as e:
        logger.error(f"Error in retry_failed_notifications: {str(e)}")

# API Routes

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'services': {
            'supabase': bool(supabase),
            'stripe': bool(STRIPE_SECRET_KEY),
            'resend': bool(RESEND_API_KEY),
            'whatsapp': bool(WHATSAPP_WEBHOOK_URL)
        }
    })

# Pricing endpoint for frontend dynamic loading
@app.route('/pricing', methods=['GET'])
def get_pricing():
    """Get current pricing from database for frontend - normalized JSON format"""
    try:
        vehicle_types = ['executive_sedan', 'luxury_suv', 'sprinter_van']
        pricing = {}
        
        for vehicle_type in vehicle_types:
            pricing[vehicle_type] = get_pricing_from_db(vehicle_type)
        
        return jsonify({'pricing': pricing}), 200
        
    except Exception as e:
        logger.error(f"Get pricing error: {str(e)}")
        return jsonify({'error': 'Failed to fetch pricing'}), 500

# Authentication endpoints
@app.route('/auth/register', methods=['POST'])
@limiter.limit("5 per minute")
def register():
    """Register new user using Supabase Auth with consistent role handling"""
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        full_name = data.get('full_name')
        phone = data.get('phone')
        role = data.get('role', 'customer')
        
        if not all([email, password, full_name]):
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Create user in Supabase Auth (source of truth) with role in metadata
        auth_response = supabase.auth.sign_up({
            'email': email,
            'password': password,
            'options': {
                'data': {
                    'full_name': full_name,
                    'phone': phone,
                    'role': role
                }
            }
        })
        
        if auth_response.user:
            user_id = auth_response.user.id
            
            # Split full_name for schema compliance
            name_parts = full_name.split(' ', 1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ''
            
            # Insert into appropriate table based on role with consistent IDs
            if role == 'driver':
                driver_data = {
                    'id': user_id,  # Consistent with Supabase Auth ID
                    'driver_id': generate_driver_id(),
                    'email': email,
                    'first_name': first_name,
                    'last_name': last_name,
                    'phone': phone or '',
                    'employment_status': 'pending',
                    'account_status': 'pending'
                }
                supabase.table('drivers').insert(driver_data).execute()
            elif role == 'admin':
                admin_data = {
                    'id': user_id,  # Consistent with Supabase Auth ID
                    'email': email,
                    'first_name': first_name,
                    'last_name': last_name,
                    'role': 'admin'
                }
                supabase.table('admin_users').insert(admin_data).execute()
            else:
                # Customer
                user_data = {
                    'id': user_id,  # Consistent with Supabase Auth ID
                    'email': email,
                    'first_name': first_name,
                    'last_name': last_name,
                    'phone': phone
                }
                supabase.table('users').insert(user_data).execute()
            
            # Create audit log
            create_audit_log(
                user_id, 
                role, 
                'user_registered',
                'user',
                user_id,
                {'email': email, 'role': role}
            )
            
            # Create welcome notification
            notification = create_notification(
                user_id,
                role,
                'welcome',
                'Welcome to BLuxA Corp',
                f'Welcome {full_name}! Your {role} account has been created successfully.',
                {'email': email, 'role': role}
            )
            
            # Send welcome email
            if notification:
                email_content = f"""
                <h2>Welcome to BLuxA Corp!</h2>
                <p>Dear {full_name},</p>
                <p>Your {role} account has been created successfully.</p>
                <p>You can now access our premium transportation services.</p>
                <p>Thank you for choosing BLuxA Corp!</p>
                """
                send_email_with_retry(email, 'Welcome to BLuxA Corp', email_content, notification['id'])
            
            return jsonify({
                'message': 'User registered successfully',
                'user': {
                    'id': user_id,
                    'email': email,
                    'full_name': full_name,
                    'role': role
                }
            }), 201
        else:
            return jsonify({'error': 'Registration failed'}), 400
            
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        return jsonify({'error': 'Registration failed'}), 500

@app.route('/auth/login', methods=['POST'])
@limiter.limit("10 per minute")
def login():
    """User login using Supabase Auth"""
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        
        if not all([email, password]):
            return jsonify({'error': 'Email and password required'}), 400
        
        # Authenticate with Supabase Auth (source of truth)
        auth_response = supabase.auth.sign_in_with_password({
            'email': email,
            'password': password
        })
        
        if auth_response.user and auth_response.session:
            user = auth_response.user
            role = user.user_metadata.get('role', 'customer')
            
            # Create audit log
            create_audit_log(
                user.id,
                role,
                'user_login',
                'user',
                user.id,
                {'email': email}
            )
            
            return jsonify({
                'message': 'Login successful',
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'role': role,
                    'full_name': user.user_metadata.get('full_name', ''),
                    'phone': user.user_metadata.get('phone', '')
                },
                'access_token': auth_response.session.access_token,
                'refresh_token': auth_response.session.refresh_token
            }), 200
        else:
            return jsonify({'error': 'Invalid credentials'}), 401
            
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return jsonify({'error': 'Login failed'}), 500

# Booking endpoints with consistent ID handling
@app.route('/bookings', methods=['POST'])
@limiter.limit("20 per hour")
def create_booking():
    """Create new booking with database-driven pricing and consistent ID handling"""
    try:
        data = request.get_json()
        
        # Extract booking data - frontend to backend field mapping
        pickup_address = data.get('pickup_location')  # Frontend: pickup_location -> Backend: pickup_address
        destination_address = data.get('destination')
        pickup_date = data.get('pickup_date')  # Schema: separate fields
        pickup_time = data.get('pickup_time')  # Schema: separate fields
        vehicle_type = data.get('vehicle_type', 'executive_sedan')
        customer_name = data.get('customer_name')
        customer_email = data.get('customer_email')
        customer_phone = data.get('customer_phone')
        estimated_duration = data.get('estimated_duration', 60)  # minutes
        special_requests = data.get('special_instructions', '')  # Frontend: special_instructions -> Schema: special_requests
        
        # Validate required fields
        if not all([pickup_address, destination_address, pickup_date, pickup_time, 
                   customer_name, customer_email, customer_phone]):
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Calculate pricing using database source of truth
        is_airport_transfer = 'airport' in pickup_address.lower() or 'airport' in destination_address.lower()
        total_price = calculate_price(vehicle_type, estimated_duration, is_airport_transfer)
        
        # Generate booking ID and confirmation code
        booking_id = generate_booking_id()
        confirmation_code = str(uuid.uuid4())[:8].upper()
        
        # Create booking record with exact schema field names
        booking_data = {
            'booking_id': booking_id,  # Human-readable format (BLX...)
            'pickup_address': pickup_address,
            'destination_address': destination_address,
            'pickup_date': pickup_date,  # Schema field
            'pickup_time': pickup_time,  # Schema field
            'vehicle_type': vehicle_type,
            'customer_name': customer_name,
            'customer_email': customer_email,
            'customer_phone': customer_phone,
            'estimated_duration': estimated_duration,
            'base_price': total_price,
            'total_amount': total_price,
            'status': 'pending',
            'special_requests': special_requests,  # Schema field
            'confirmation_code': confirmation_code,
            'payment_status': 'pending'
        }
        
        # Insert booking into database
        booking_result = supabase.table('bookings').insert(booking_data).execute()
        
        if booking_result.data:
            booking = booking_result.data[0]
            
            # Create audit log
            create_audit_log(
                booking['customer_email'],
                'customer',
                'booking_created',
                'booking',
                booking['id'],  # UUID for internal reference
                {'booking_id': booking_id, 'total_amount': total_price}
            )
            
            # Create notification
            notification = create_notification(
                booking['customer_email'],
                'customer',
                'booking_confirmation',
                f'Booking Confirmation - {booking_id}',
                f'Your luxury transportation booking {booking_id} has been created successfully.',
                {'booking_id': booking_id, 'total_amount': total_price, 'phone': customer_phone}
            )
            
            # Send confirmation email with retry
            email_subject = f"Booking Confirmation - {booking_id}"
            email_content = f"""
            <h2>Booking Confirmation</h2>
            <p>Dear {customer_name},</p>
            <p>Your luxury transportation has been booked successfully!</p>
            
            <h3>Booking Details:</h3>
            <ul>
                <li><strong>Booking ID:</strong> {booking_id}</li>
                <li><strong>Pickup:</strong> {pickup_address}</li>
                <li><strong>Destination:</strong> {destination_address}</li>
                <li><strong>Date:</strong> {pickup_date}</li>
                <li><strong>Time:</strong> {pickup_time}</li>
                <li><strong>Vehicle:</strong> {vehicle_type.replace('_', ' ').title()}</li>
                <li><strong>Total Amount:</strong> ${total_price:.2f}</li>
                <li><strong>Confirmation Code:</strong> {confirmation_code}</li>
            </ul>
            
            <p>Please proceed with payment to confirm your booking.</p>
            <p>Thank you for choosing BLuxA Corp!</p>
            """
            
            send_email_with_retry(customer_email, email_subject, email_content, notification['id'] if notification else None)
            
            # Send WhatsApp notification with retry
            whatsapp_message = f"BLuxA Corp: Your booking {booking_id} is created! Pickup: {pickup_address} on {pickup_date} at {pickup_time}. Total: ${total_price:.2f}. Please complete payment to confirm."
            send_whatsapp_with_retry(customer_phone, whatsapp_message, notification['id'] if notification else None)
            
            return jsonify({
                'message': 'Booking created successfully',
                'booking': booking,  # Contains both 'id' (UUID) and 'booking_id' (BLX...)
                'payment_required': True
            }), 201
        else:
            return jsonify({'error': 'Failed to create booking'}), 500
            
    except Exception as e:
        logger.error(f"Booking creation error: {str(e)}")
        return jsonify({'error': 'Failed to create booking'}), 500

@app.route('/bookings', methods=['GET'])
@auth_required()
def get_bookings():
    """Get bookings based on user role with proper access control"""
    try:
        user_role = request.user_role
        user_id = request.user.id
        
        if user_role == 'admin':
            # Admin can see all bookings
            bookings = supabase.table('bookings').select('*').order('created_at', desc=True).execute()
        elif user_role == 'driver':
            # Driver can see assigned bookings
            bookings = supabase.table('bookings').select('*').eq('driver_id', user_id).order('created_at', desc=True).execute()
        else:
            # Customer can see their own bookings
            bookings = supabase.table('bookings').select('*').eq('user_id', user_id).order('created_at', desc=True).execute()
        
        return jsonify({
            'bookings': bookings.data,
            'count': len(bookings.data)
        }), 200
        
    except Exception as e:
        logger.error(f"Get bookings error: {str(e)}")
        return jsonify({'error': 'Failed to fetch bookings'}), 500

@app.route('/bookings/<booking_id>/status', methods=['PUT'])
@auth_required(['admin', 'driver'])
def update_booking_status(booking_id):
    """Update booking status with complete audit logging"""
    try:
        data = request.get_json()
        new_status = data.get('status')
        
        if not new_status:
            return jsonify({'error': 'Status is required'}), 400
        
        # Get current booking
        current_booking = supabase.table('bookings').select('*').eq('id', booking_id).execute()
        if not current_booking.data:
            return jsonify({'error': 'Booking not found'}), 404
        
        booking = current_booking.data[0]
        old_status = booking['status']
        
        # Update booking status
        result = supabase.table('bookings').update({
            'status': new_status,
            'updated_at': datetime.now().isoformat()
        }).eq('id', booking_id).execute()
        
        if result.data:
            updated_booking = result.data[0]
            
            # Create audit log
            create_audit_log(
                request.user.id,
                request.user_role,
                'booking_status_updated',
                'booking',
                booking_id,
                {'old_status': old_status, 'new_status': new_status, 'booking_id': booking['booking_id']}
            )
            
            # Create notification
            notification = create_notification(
                booking['customer_email'],
                'customer',
                'status_update',
                f'Booking Status Update - {booking["booking_id"]}',
                f'Your booking status has been updated to: {new_status.title()}',
                {'booking_id': booking['booking_id'], 'old_status': old_status, 'new_status': new_status, 'phone': booking['customer_phone']}
            )
            
            # Send status update notifications with retry
            email_subject = f"Booking Status Update - {booking['booking_id']}"
            email_content = f"""
            <h2>Booking Status Update</h2>
            <p>Dear {booking['customer_name']},</p>
            <p>Your booking status has been updated to: <strong>{new_status.title()}</strong></p>
            
            <h3>Booking Details:</h3>
            <ul>
                <li><strong>Booking ID:</strong> {booking['booking_id']}</li>
                <li><strong>Status:</strong> {new_status.title()}</li>
                <li><strong>Pickup:</strong> {booking['pickup_address']}</li>
                <li><strong>Destination:</strong> {booking['destination_address']}</li>
                <li><strong>Date:</strong> {booking['pickup_date']}</li>
                <li><strong>Time:</strong> {booking['pickup_time']}</li>
            </ul>
            
            <p>Thank you for choosing BLuxA Corp!</p>
            """
            
            send_email_with_retry(booking['customer_email'], email_subject, email_content, notification['id'] if notification else None)
            
            return jsonify({
                'message': 'Booking status updated successfully',
                'booking': updated_booking
            }), 200
        else:
            return jsonify({'error': 'Failed to update booking'}), 500
            
    except Exception as e:
        logger.error(f"Update booking status error: {str(e)}")
        return jsonify({'error': 'Failed to update booking status'}), 500

# Payment endpoints with consistent ID handling
@app.route('/payments/create-intent', methods=['POST'])
@limiter.limit("30 per hour")
def create_payment_intent():
    """Create Stripe payment intent with proper payment record - uses booking UUID"""
    try:
        data = request.get_json()
        booking_id = data.get('booking_id')  # This should be the UUID from booking.id
        
        if not booking_id:
            return jsonify({'error': 'Booking ID is required'}), 400
        
        # Get booking details using UUID
        booking_result = supabase.table('bookings').select('*').eq('id', booking_id).execute()
        
        if not booking_result.data:
            return jsonify({'error': 'Booking not found'}), 404
        
        booking = booking_result.data[0]
        amount_cents = int(float(booking['total_amount']) * 100)  # Convert to cents
        
        # Create Stripe payment intent
        payment_intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency='usd',
            metadata={
                'booking_id': booking_id,  # UUID for internal reference
                'booking_reference': booking['booking_id'],  # Human-readable reference
                'customer_email': booking['customer_email']
            }
        )
        
        # Create payment record with exact schema fields
        payment_data = {
            'payment_id': generate_payment_id(),
            'booking_id': booking_id,  # UUID reference to bookings table
            'amount': booking['total_amount'],
            'currency': 'USD',
            'payment_method': 'credit_card',
            'payment_status': 'pending',
            'transaction_id': payment_intent.id,
            'gateway_transaction_id': payment_intent.id,
            'gateway_name': 'stripe',
            'description': f"Payment for booking {booking['booking_id']}"
        }
        
        payment_result = supabase.table('payments').insert(payment_data).execute()
        
        if payment_result.data:
            # Create audit log
            create_audit_log(
                booking['customer_email'],
                'customer',
                'payment_intent_created',
                'payment',
                payment_result.data[0]['id'],
                {'payment_id': payment_data['payment_id'], 'amount': booking['total_amount']}
            )
        
        return jsonify({
            'client_secret': payment_intent.client_secret,
            'payment_intent_id': payment_intent.id,
            'amount': booking['total_amount']
        }), 200
        
    except Exception as e:
        logger.error(f"Create payment intent error: {str(e)}")
        return jsonify({'error': 'Failed to create payment intent'}), 500

@app.route('/webhooks/stripe', methods=['POST'])
def stripe_webhook():
    """Handle Stripe webhooks with complete payment flow"""
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError:
        return jsonify({'error': 'Invalid signature'}), 400
    
    # Handle payment success
    if event['type'] == 'payment_intent.succeeded':
        payment_intent = event['data']['object']
        booking_id = payment_intent['metadata'].get('booking_id')  # UUID
        
        if booking_id:
            # Update payment status in payments table
            payment_update = supabase.table('payments').update({
                'payment_status': 'completed',
                'processed_at': datetime.now().isoformat(),
                'gateway_transaction_id': payment_intent['id']
            }).eq('transaction_id', payment_intent['id']).execute()
            
            # Update booking status
            booking_update = supabase.table('bookings').update({
                'payment_status': 'paid',
                'status': 'confirmed',
                'updated_at': datetime.now().isoformat()
            }).eq('id', booking_id).execute()
            
            if booking_update.data:
                booking = booking_update.data[0]
                
                # Create audit log
                create_audit_log(
                    booking['customer_email'],
                    'customer',
                    'payment_completed',
                    'payment',
                    booking_id,
                    {'booking_id': booking['booking_id'], 'amount': payment_intent['amount'] / 100}
                )
                
                # Create notification
                notification = create_notification(
                    booking['customer_email'],
                    'customer',
                    'payment_confirmation',
                    f'Payment Confirmed - {booking["booking_id"]}',
                    f'Your payment of ${payment_intent["amount"] / 100:.2f} has been processed successfully.',
                    {'booking_id': booking['booking_id'], 'amount': payment_intent['amount'] / 100, 'phone': booking['customer_phone']}
                )
                
                # Send payment confirmation with retry
                email_subject = f"Payment Confirmed - {booking['booking_id']}"
                email_content = f"""
                <h2>Payment Confirmation</h2>
                <p>Dear {booking['customer_name']},</p>
                <p>Your payment has been processed successfully!</p>
                
                <h3>Payment Details:</h3>
                <ul>
                    <li><strong>Booking ID:</strong> {booking['booking_id']}</li>
                    <li><strong>Amount Paid:</strong> ${payment_intent['amount'] / 100:.2f}</li>
                    <li><strong>Payment Method:</strong> Credit Card</li>
                    <li><strong>Status:</strong> Confirmed</li>
                    <li><strong>Date:</strong> {booking['pickup_date']}</li>
                    <li><strong>Time:</strong> {booking['pickup_time']}</li>
                </ul>
                
                <p>Your ride is now confirmed and we will assign a driver shortly.</p>
                <p>Thank you for choosing BLuxA Corp!</p>
                """
                
                send_email_with_retry(booking['customer_email'], email_subject, email_content, notification['id'] if notification else None)
                
                # Send WhatsApp confirmation with retry
                whatsapp_message = f"BLuxA Corp: Payment confirmed! Your booking {booking['booking_id']} is now confirmed. We will assign a driver and send details soon."
                send_whatsapp_with_retry(booking['customer_phone'], whatsapp_message, notification['id'] if notification else None)
    
    return jsonify({'status': 'success'}), 200

# Enhanced Admin endpoints with strict security
@app.route('/admin/dashboard', methods=['GET'])
@auth_required(['admin'])
def admin_dashboard():
    """Get admin dashboard data with comprehensive metrics"""
    try:
        # Get statistics
        total_bookings = supabase.table('bookings').select('id', count='exact').execute()
        active_drivers = supabase.table('drivers').select('id', count='exact').eq('account_status', 'active').execute()
        total_vehicles = supabase.table('vehicles').select('id', count='exact').eq('status', 'available').execute()
        pending_bookings = supabase.table('bookings').select('id', count='exact').eq('status', 'pending').execute()
        
        # Get recent bookings
        recent_bookings = supabase.table('bookings').select('*').order('created_at', desc=True).limit(10).execute()
        
        # Calculate revenue (this month)
        current_month = datetime.now().strftime('%Y-%m')
        monthly_revenue = supabase.table('bookings').select('total_amount').gte('created_at', f'{current_month}-01').eq('payment_status', 'paid').execute()
        
        total_revenue = sum(float(booking['total_amount']) for booking in monthly_revenue.data)
        
        return jsonify({
            'stats': {
                'total_bookings': total_bookings.count,
                'active_drivers': active_drivers.count,
                'total_vehicles': total_vehicles.count,
                'pending_bookings': pending_bookings.count,
                'monthly_revenue': total_revenue,
                'average_rating': 4.9  # This would be calculated from actual ratings
            },
            'recent_bookings': recent_bookings.data
        }), 200
        
    except Exception as e:
        logger.error(f"Admin dashboard error: {str(e)}")
        return jsonify({'error': 'Failed to fetch dashboard data'}), 500

# PATCHED ADMIN ENDPOINTS - Enhanced vehicle and driver management

@app.route('/admin/vehicles', methods=['GET'])
@auth_required(['admin'])
@limiter.limit("120 per hour")
def admin_list_vehicles():
    """List all vehicles with optional status filter"""
    status = request.args.get('status')  # optional filter
    q = supabase.table('vehicles').select('*')
    if status:
        q = q.eq('status', status)
    r = q.order('created_at', desc=True).execute()
    return jsonify({'vehicles': r.data or []}), 200

@app.route('/admin/vehicles', methods=['POST'])
@auth_required(['admin'])
@limiter.limit("30 per hour")
def admin_create_vehicle():
    """Create new vehicle with consistent ID generation"""
    data = request.get_json() or {}
    # Minimal fields; others optional
    required = ['make', 'model', 'year', 'license_plate', 'vin', 'vehicle_type', 'passenger_capacity']
    if not all(data.get(k) for k in required):
        return jsonify({'error': 'Missing required vehicle fields'}), 400

    # Generate VEH id if not provided
    def _next_vehicle_id():
        res = supabase.table('vehicles').select('vehicle_id').order('created_at', desc=True).limit(1).execute()
        if res.data:
            last = res.data[0]['vehicle_id']  # e.g., "VEH012"
            try:
                num = int(last[3:]) + 1
            except Exception:
                num = 1
        else:
            num = 1
        return f'VEH{num:03d}'

    vehicle_payload = {
        'vehicle_id': data.get('vehicle_id') or _next_vehicle_id(),
        'make': data['make'],
        'model': data['model'],
        'year': int(data['year']),
        'color': data.get('color'),
        'license_plate': data['license_plate'],
        'vin': data['vin'],
        'vehicle_type': data['vehicle_type'],
        'passenger_capacity': int(data['passenger_capacity']),
        'luggage_capacity': int(data.get('luggage_capacity', 0)),
        'base_rate': float(data.get('base_rate', 25.00)),
        'per_hour_rate': float(data.get('per_hour_rate', 65.00)),
        'airport_surcharge': float(data.get('airport_surcharge', 10.00)),
        'minimum_charge': float(data.get('minimum_charge', 50.00)),
        'status': data.get('status', 'available'),
        'features': data.get('features', []),
        'amenities': data.get('amenities', []),
        'images': data.get('images', []),
    }

    r = supabase.table('vehicles').insert(vehicle_payload).execute()
    if not r.data:
        return jsonify({'error': 'Failed to create vehicle'}), 500

    v = r.data[0]
    create_audit_log(request.user.id, 'admin', 'vehicle_created', 'vehicle', v['id'], {'vehicle_id': v['vehicle_id']})
    create_notification(request.user.id, 'admin', 'vehicle_created', 'Vehicle Added', f"Vehicle {v['vehicle_id']} created.", {'vehicle_id': v['vehicle_id']})
    return jsonify({'vehicle': v}), 201

@app.route('/admin/vehicles/<vehicle_uuid>', methods=['PUT'])
@auth_required(['admin'])
@limiter.limit("60 per hour")
def admin_update_vehicle(vehicle_uuid):
    """Update vehicle with audit logging"""
    data = request.get_json() or {}
    # Only allow safe fields
    allowed_fields = {
        'color', 'status', 'base_rate', 'per_hour_rate', 'airport_surcharge',
        'minimum_charge', 'features', 'amenities', 'images', 'passenger_capacity',
        'luggage_capacity', 'make', 'model', 'year', 'vehicle_type', 'license_plate'
    }
    update_payload = {k: data[k] for k in data.keys() if k in allowed_fields}
    if not update_payload:
        return jsonify({'error': 'No allowed fields to update'}), 400

    r = supabase.table('vehicles').update(update_payload).eq('id', vehicle_uuid).execute()
    if not r.data:
        return jsonify({'error': 'Vehicle not found or update failed'}), 404

    v = r.data[0]
    create_audit_log(request.user.id, 'admin', 'vehicle_updated', 'vehicle', vehicle_uuid, {'changes': update_payload, 'vehicle_id': v.get('vehicle_id')})
    create_notification(request.user.id, 'admin', 'vehicle_updated', 'Vehicle Updated', f"Vehicle {v.get('vehicle_id','')} updated.", {'vehicle_id': v.get('vehicle_id')})
    return jsonify({'vehicle': v}), 200

@app.route('/admin/drivers', methods=['GET'])
@auth_required(['admin'])
@limiter.limit("120 per hour")
def admin_list_drivers():
    """List all drivers with optional status filter"""
    status = request.args.get('status')  # optional filter
    q = supabase.table('drivers').select('*')
    if status:
        q = q.eq('employment_status', status)
    r = q.order('created_at', desc=True).execute()
    return jsonify({'drivers': r.data or []}), 200

@app.route('/admin/drivers', methods=['POST'])
@auth_required(['admin'])
@limiter.limit("30 per hour")
def admin_create_driver():
    """Create new driver with consistent ID generation"""
    data = request.get_json() or {}
    required = ['email', 'first_name', 'last_name', 'phone']
    if not all(data.get(k) for k in required):
        return jsonify({'error': 'Missing required driver fields'}), 400

    # Generate DRV id if not provided
    def _next_driver_id():
        res = supabase.table('drivers').select('driver_id').order('created_at', desc=True).limit(1).execute()
        if res.data:
            last = res.data[0]['driver_id']  # e.g., "DRV012"
            try:
                num = int(last[3:]) + 1
            except Exception:
                num = 1
        else:
            num = 1
        return f'DRV{num:03d}'

    driver_payload = {
        'driver_id': data.get('driver_id') or _next_driver_id(),
        'email': data['email'],
        'first_name': data['first_name'],
        'last_name': data['last_name'],
        'phone': data['phone'],
        'employment_status': data.get('employment_status', 'pending'),
        'account_status': data.get('account_status', 'pending'),
        'status': data.get('status', 'offline'),
        'hourly_rate': float(data.get('hourly_rate', 20.00)),
        'commission_rate': float(data.get('commission_rate', 80.00)),
    }

    r = supabase.table('drivers').insert(driver_payload).execute()
    if not r.data:
        return jsonify({'error': 'Failed to create driver'}), 500

    d = r.data[0]
    create_audit_log(request.user.id, 'admin', 'driver_created', 'driver', d['id'], {'driver_id': d['driver_id']})
    create_notification(request.user.id, 'admin', 'driver_created', 'Driver Added', f"Driver {d['driver_id']} created.", {'driver_id': d['driver_id']})
    return jsonify({'driver': d}), 201

@app.route('/admin/drivers/<driver_uuid>', methods=['PUT'])
@auth_required(['admin'])
@limiter.limit("60 per hour")
def admin_update_driver(driver_uuid):
    """Update driver with audit logging"""
    data = request.get_json() or {}
    allowed_fields = {
        'employment_status', 'account_status', 'status', 'hourly_rate', 'commission_rate',
        'phone', 'first_name', 'last_name'
    }
    update_payload = {k: data[k] for k in data.keys() if k in allowed_fields}
    if not update_payload:
        return jsonify({'error': 'No allowed fields to update'}), 400

    r = supabase.table('drivers').update(update_payload).eq('id', driver_uuid).execute()
    if not r.data:
        return jsonify({'error': 'Driver not found or update failed'}), 404

    d = r.data[0]
    create_audit_log(request.user.id, 'admin', 'driver_updated', 'driver', driver_uuid, {'changes': update_payload, 'driver_id': d.get('driver_id')})
    create_notification(request.user.id, 'admin', 'driver_updated', 'Driver Updated', f"Driver {d.get('driver_id','')} updated.", {'driver_id': d.get('driver_id')})
    return jsonify({'driver': d}), 200

# Vehicle assignment endpoints
@app.route('/admin/assignments', methods=['GET'])
@auth_required(['admin'])
@limiter.limit("120 per hour")
def list_assignments():
    """List vehicle assignments with optional active filter"""
    active = request.args.get('active')
    q = supabase.table('vehicle_assignments').select('*').order('created_at', desc=True)
    if active is not None:
        q = q.eq('is_active', active.lower() in ['1', 'true', 'yes'])
    r = q.execute()
    return jsonify({'assignments': r.data or []}), 200

@app.route('/admin/assignments', methods=['POST'])
@auth_required(['admin'])
@limiter.limit("30 per hour")
def create_assignment():
    """Create vehicle assignment with audit logging"""
    data = request.get_json() or {}
    required = ['driver_id', 'vehicle_id', 'assigned_date']
    if not all(data.get(k) for k in required):
        return jsonify({'error': 'driver_id, vehicle_id, assigned_date are required'}), 400

    payload = {
        'driver_id': data['driver_id'],
        'vehicle_id': data['vehicle_id'],
        'assigned_date': data['assigned_date'],
        'notes': data.get('notes', ''),
        'is_active': True
    }
    r = supabase.table('vehicle_assignments').insert(payload).execute()
    if not r.data:
        return jsonify({'error': 'Failed to create assignment'}), 500

    a = r.data[0]
    # Optionally mark driver status / vehicle status
    supabase.table('drivers').update({'status': 'available'}).eq('id', data['driver_id']).execute()
    supabase.table('vehicles').update({'status': 'available'}).eq('id', data['vehicle_id']).execute()

    create_audit_log(request.user.id, 'admin', 'assignment_created', 'vehicle_assignment', a['id'], {'driver_id': data['driver_id'], 'vehicle_id': data['vehicle_id']})
    create_notification(request.user.id, 'admin', 'assignment_created', 'Driver Assigned', 'Driver assigned to vehicle.', {'driver_id': data['driver_id'], 'vehicle_id': data['vehicle_id']})
    return jsonify({'assignment': a}), 201

@app.route('/admin/assignments/<assignment_uuid>', methods=['PUT'])
@auth_required(['admin'])
@limiter.limit("60 per hour")
def close_assignment(assignment_uuid):
    """Close vehicle assignment with audit logging"""
    data = request.get_json() or {}
    unassigned_date = data.get('unassigned_date') or datetime.utcnow().date().isoformat()

    r = supabase.table('vehicle_assignments').update({
        'is_active': False,
        'unassigned_date': unassigned_date
    }).eq('id', assignment_uuid).execute()
    if not r.data:
        return jsonify({'error': 'Assignment not found or update failed'}), 404

    a = r.data[0]
    create_audit_log(request.user.id, 'admin', 'assignment_closed', 'vehicle_assignment', assignment_uuid, {'unassigned_date': unassigned_date})
    create_notification(request.user.id, 'admin', 'assignment_closed', 'Driver Unassigned', 'Driver unassigned from vehicle.', {'assignment_id': assignment_uuid})
    return jsonify({'assignment': a}), 200

@app.route('/admin/settings', methods=['GET', 'POST'])
@auth_required(['admin'])
def admin_settings():
    """Get or update admin settings using system_settings table"""
    try:
        if request.method == 'GET':
            # Get all settings
            settings = supabase.table('system_settings').select('*').execute()
            return jsonify({'settings': settings.data}), 200
        
        elif request.method == 'POST':
            data = request.get_json()
            setting_key = data.get('setting_key')
            setting_value = data.get('setting_value')
            setting_type = data.get('setting_type', 'string')
            category = data.get('category', 'general')
            
            if not all([setting_key, setting_value]):
                return jsonify({'error': 'Setting key and value are required'}), 400
            
            # Upsert setting
            result = supabase.table('system_settings').upsert({
                'setting_key': setting_key,
                'setting_value': setting_value,
                'setting_type': setting_type,
                'category': category,
                'updated_at': datetime.now().isoformat(),
                'updated_by': request.user.id
            }).execute()
            
            # Create audit log
            create_audit_log(
                request.user.id,
                'admin',
                'setting_updated',
                'system_settings',
                setting_key,
                {'setting_key': setting_key, 'setting_value': setting_value}
            )
            
            return jsonify({
                'message': 'Setting updated successfully',
                'setting': result.data[0] if result.data else None
            }), 200
            
    except Exception as e:
        logger.error(f"Admin settings error: {str(e)}")
        return jsonify({'error': 'Failed to manage settings'}), 500

@app.route('/admin/assign-driver', methods=['POST'])
@auth_required(['admin'])
def assign_driver():
    """Assign driver to booking with complete notifications"""
    try:
        data = request.get_json()
        booking_id = data.get('booking_id')
        driver_id = data.get('driver_id')
        
        if not all([booking_id, driver_id]):
            return jsonify({'error': 'Booking ID and Driver ID are required'}), 400
        
        # Get booking details
        booking_result = supabase.table('bookings').select('*').eq('id', booking_id).execute()
        if not booking_result.data:
            return jsonify({'error': 'Booking not found'}), 404
        
        booking = booking_result.data[0]
        
        # Update booking with driver assignment
        result = supabase.table('bookings').update({
            'driver_id': driver_id,
            'status': 'assigned',
            'updated_at': datetime.now().isoformat()
        }).eq('id', booking_id).execute()
        
        if result.data:
            updated_booking = result.data[0]
            
            # Get driver details
            driver_result = supabase.table('drivers').select('*').eq('id', driver_id).execute()
            if driver_result.data:
                driver = driver_result.data[0]
                
                # Create audit log
                create_audit_log(
                    request.user.id,
                    'admin',
                    'driver_assigned',
                    'booking',
                    booking_id,
                    {'booking_id': booking['booking_id'], 'driver_id': driver['driver_id']}
                )
                
                # Create notifications
                customer_notification = create_notification(
                    booking['customer_email'],
                    'customer',
                    'driver_assigned',
                    f'Driver Assigned - {booking["booking_id"]}',
                    f'Professional driver {driver["first_name"]} {driver["last_name"]} has been assigned to your booking.',
                    {'booking_id': booking['booking_id'], 'driver_name': f'{driver["first_name"]} {driver["last_name"]}', 'phone': booking['customer_phone']}
                )
                
                driver_notification = create_notification(
                    driver['id'],
                    'driver',
                    'booking_assigned',
                    f'New Booking Assignment - {booking["booking_id"]}',
                    f'You have been assigned to booking {booking["booking_id"]}.',
                    {'booking_id': booking['booking_id']}
                )
                
                # Send assignment notification to customer with retry
                email_subject = f"Driver Assigned - {booking['booking_id']}"
                email_content = f"""
                <h2>Driver Assigned</h2>
                <p>Dear {booking['customer_name']},</p>
                <p>A professional driver has been assigned to your booking!</p>
                
                <h3>Driver Details:</h3>
                <ul>
                    <li><strong>Name:</strong> {driver['first_name']} {driver['last_name']}</li>
                    <li><strong>Phone:</strong> {driver['phone']}</li>
                    <li><strong>Rating:</strong> {driver['rating']}/5.0</li>
                </ul>
                
                <h3>Booking Details:</h3>
                <ul>
                    <li><strong>Pickup:</strong> {booking['pickup_address']}</li>
                    <li><strong>Destination:</strong> {booking['destination_address']}</li>
                    <li><strong>Date:</strong> {booking['pickup_date']}</li>
                    <li><strong>Time:</strong> {booking['pickup_time']}</li>
                </ul>
                
                <p>Your driver will contact you before pickup.</p>
                <p>Thank you for choosing BLuxA Corp!</p>
                """
                
                send_email_with_retry(booking['customer_email'], email_subject, email_content, customer_notification['id'] if customer_notification else None)
                
                # Send assignment notification to driver with retry
                driver_email_subject = f"New Booking Assignment - {booking['booking_id']}"
                driver_email_content = f"""
                <h2>New Booking Assignment</h2>
                <p>Dear {driver['first_name']},</p>
                <p>You have been assigned to a new booking!</p>
                
                <h3>Booking Details:</h3>
                <ul>
                    <li><strong>Booking ID:</strong> {booking['booking_id']}</li>
                    <li><strong>Customer:</strong> {booking['customer_name']}</li>
                    <li><strong>Phone:</strong> {booking['customer_phone']}</li>
                    <li><strong>Pickup:</strong> {booking['pickup_address']}</li>
                    <li><strong>Destination:</strong> {booking['destination_address']}</li>
                    <li><strong>Date:</strong> {booking['pickup_date']}</li>
                    <li><strong>Time:</strong> {booking['pickup_time']}</li>
                </ul>
                
                <p>Please contact the customer before pickup time.</p>
                <p>Good luck with your ride!</p>
                """
                
                send_email_with_retry(driver['email'], driver_email_subject, driver_email_content, driver_notification['id'] if driver_notification else None)
            
            return jsonify({
                'message': 'Driver assigned successfully',
                'booking': updated_booking
            }), 200
        else:
            return jsonify({'error': 'Failed to assign driver'}), 500
            
    except Exception as e:
        logger.error(f"Assign driver error: {str(e)}")
        return jsonify({'error': 'Failed to assign driver'}), 500

# Notification retry endpoint (PATCHED VERSION)
@app.route('/admin/notifications/retry', methods=['POST'])
@auth_required(['admin'])
@limiter.limit("10 per hour")
def trigger_notification_retry():
    """
    Triggers retry of failed notifications that have not exceeded max_retries.
    This endpoint is meant for scheduled calls (e.g., Cloud Scheduler) or manual use.
    """
    # Run retry in background to avoid long-running request
    t = threading.Thread(target=retry_failed_notifications, daemon=True)
    t.start()

    create_audit_log(request.user.id, 'admin', 'notifications_retry_triggered', 'notification', None, {})
    return jsonify({'message': 'Notification retry started'}), 202

# Driver endpoints
@app.route('/driver/dashboard', methods=['GET'])
@auth_required(['driver'])
def driver_dashboard():
    """Get driver dashboard data"""
    try:
        user_id = request.user.id
        
        # Get driver details
        driver_result = supabase.table('drivers').select('*').eq('id', user_id).execute()
        if not driver_result.data:
            return jsonify({'error': 'Driver profile not found'}), 404
        
        driver = driver_result.data[0]
        
        # Get today's rides
        today = datetime.now().date().isoformat()
        today_rides = supabase.table('bookings').select('*').eq('driver_id', user_id).eq('pickup_date', today).execute()
        
        # Get this week's earnings
        week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).date().isoformat()
        week_earnings = supabase.table('bookings').select('total_amount').eq('driver_id', user_id).gte('pickup_date', week_start).eq('status', 'completed').execute()
        
        total_earnings = sum(float(booking['total_amount']) * (driver['commission_rate'] / 100) for booking in week_earnings.data)
        
        return jsonify({
            'driver': driver,
            'stats': {
                'today_rides': len(today_rides.data),
                'total_rides': driver['total_rides'],
                'week_earnings': total_earnings,
                'rating': driver['rating']
            },
            'today_schedule': today_rides.data
        }), 200
        
    except Exception as e:
        logger.error(f"Driver dashboard error: {str(e)}")
        return jsonify({'error': 'Failed to fetch driver dashboard'}), 500

# Seed super admin endpoint (for initial setup)
@app.route('/seed/super-admin', methods=['POST'])
def seed_super_admin():
    """Create initial super admin account (secured with token)"""
    try:
        # Security check with seed token
        seed_token = request.headers.get('X-Seed-Token')
        if seed_token != os.getenv('SEED_TOKEN', 'bluxa-seed-2024'):
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Check if super admin already exists
        existing_admin = supabase.table('admin_users').select('*').eq('role', 'super_admin').execute()
        if existing_admin.data:
            return jsonify({'message': 'Super admin already exists'}), 200
        
        # Create super admin in Supabase Auth
        admin_email = 'admin@bluxacorp.com'
        admin_password = 'BLuxA2024Admin!'
        
        auth_response = supabase.auth.sign_up({
            'email': admin_email,
            'password': admin_password,
            'options': {
                'data': {
                    'full_name': 'BLuxA Administrator',
                    'role': 'admin'
                }
            }
        })
        
        if auth_response.user:
            # Insert into admin_users table
            admin_data = {
                'id': auth_response.user.id,
                'email': admin_email,
                'first_name': 'BLuxA',
                'last_name': 'Administrator',
                'role': 'super_admin',
                'status': 'active'
            }
            
            supabase.table('admin_users').insert(admin_data).execute()
            
            return jsonify({
                'message': 'Super admin created successfully',
                'email': admin_email,
                'password': admin_password
            }), 201
        else:
            return jsonify({'error': 'Failed to create super admin'}), 500
            
    except Exception as e:
        logger.error(f"Seed super admin error: {str(e)}")
        return jsonify({'error': 'Failed to create super admin'}), 500

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({'error': 'Rate limit exceeded', 'retry_after': str(e.retry_after)}), 429

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

# Background task to periodically retry failed notifications
def start_notification_retry_scheduler():
    """Start background scheduler for notification retries"""
    def retry_scheduler():
        while True:
            try:
                retry_failed_notifications()
                time.sleep(300)  # Retry every 5 minutes
            except Exception as e:
                logger.error(f"Notification retry scheduler error: {str(e)}")
                time.sleep(60)  # Wait 1 minute on error
    
    retry_thread = threading.Thread(target=retry_scheduler, daemon=True)
    retry_thread.start()
    logger.info("Notification retry scheduler started")

if __name__ == '__main__':
    # Start notification retry scheduler
    start_notification_retry_scheduler()
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
