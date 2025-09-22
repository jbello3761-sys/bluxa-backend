-- BLuxA Corp Transportation Management System - Production Schema
-- Enhanced with notification retry logic and pricing improvements

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create enum types
CREATE TYPE user_role AS ENUM ('customer', 'driver', 'admin');
CREATE TYPE booking_status AS ENUM ('pending', 'confirmed', 'assigned', 'in_progress', 'completed', 'cancelled');
CREATE TYPE payment_status AS ENUM ('pending', 'processing', 'paid', 'failed', 'refunded');
CREATE TYPE vehicle_status AS ENUM ('available', 'in_use', 'maintenance', 'retired');
CREATE TYPE driver_status AS ENUM ('available', 'busy', 'offline');
CREATE TYPE employment_status AS ENUM ('pending', 'active', 'inactive', 'terminated');
CREATE TYPE account_status AS ENUM ('pending', 'active', 'suspended', 'deactivated');
CREATE TYPE notification_status AS ENUM ('pending', 'sent', 'failed', 'cancelled');

-- Users table (customers) - Supabase Auth is source of truth
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    phone VARCHAR(20),
    address TEXT,
    city VARCHAR(100),
    state VARCHAR(50),
    zip_code VARCHAR(10),
    date_of_birth DATE,
    emergency_contact_name VARCHAR(200),
    emergency_contact_phone VARCHAR(20),
    preferences JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Drivers table with consistent ID format
CREATE TABLE drivers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    driver_id VARCHAR(10) UNIQUE NOT NULL, -- DRV001, DRV002, etc.
    email VARCHAR(255) UNIQUE NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    address TEXT,
    city VARCHAR(100),
    state VARCHAR(50),
    zip_code VARCHAR(10),
    date_of_birth DATE,
    license_number VARCHAR(50),
    license_expiry DATE,
    license_class VARCHAR(10),
    background_check_status VARCHAR(50) DEFAULT 'pending',
    background_check_date DATE,
    employment_status employment_status DEFAULT 'pending',
    account_status account_status DEFAULT 'pending',
    hire_date DATE,
    termination_date DATE,
    hourly_rate DECIMAL(10,2) DEFAULT 20.00,
    commission_rate DECIMAL(5,2) DEFAULT 80.00, -- Percentage
    total_rides INTEGER DEFAULT 0,
    rating DECIMAL(3,2) DEFAULT 5.00,
    total_earnings DECIMAL(12,2) DEFAULT 0.00,
    emergency_contact_name VARCHAR(200),
    emergency_contact_phone VARCHAR(20),
    vehicle_assigned VARCHAR(10), -- References vehicles.vehicle_id
    status driver_status DEFAULT 'offline',
    last_location POINT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Vehicles table with database-driven pricing
CREATE TABLE vehicles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    vehicle_id VARCHAR(10) UNIQUE NOT NULL, -- VEH001, VEH002, etc.
    make VARCHAR(50) NOT NULL,
    model VARCHAR(50) NOT NULL,
    year INTEGER NOT NULL,
    color VARCHAR(30),
    license_plate VARCHAR(20) UNIQUE NOT NULL,
    vin VARCHAR(50) UNIQUE NOT NULL,
    vehicle_type VARCHAR(50) NOT NULL, -- executive_sedan, luxury_suv, sprinter_van
    passenger_capacity INTEGER NOT NULL,
    luggage_capacity INTEGER DEFAULT 0,
    base_rate DECIMAL(10,2) NOT NULL DEFAULT 25.00, -- Base rate for pricing
    per_hour_rate DECIMAL(10,2) NOT NULL DEFAULT 65.00, -- Hourly rate
    airport_surcharge DECIMAL(10,2) DEFAULT 10.00, -- Additional airport fee
    minimum_charge DECIMAL(10,2) DEFAULT 50.00, -- Minimum booking charge
    mileage INTEGER DEFAULT 0,
    last_service_date DATE,
    next_service_date DATE,
    insurance_policy VARCHAR(100),
    insurance_expiry DATE,
    registration_expiry DATE,
    status vehicle_status DEFAULT 'available',
    features JSONB DEFAULT '[]', -- ["GPS", "WiFi", "Premium Sound"]
    amenities JSONB DEFAULT '[]', -- ["Water", "Mints", "Phone Charger"]
    images JSONB DEFAULT '[]', -- Array of image URLs
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Bookings table with separate date/time fields as requested
CREATE TABLE bookings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    booking_id VARCHAR(20) UNIQUE NOT NULL, -- BLX20241201ABC123
    user_id UUID REFERENCES users(id),
    driver_id UUID REFERENCES drivers(id),
    vehicle_id UUID REFERENCES vehicles(id),
    pickup_address TEXT NOT NULL,
    destination_address TEXT NOT NULL,
    pickup_date DATE NOT NULL, -- Separate field as requested
    pickup_time TIME NOT NULL, -- Separate field as requested
    estimated_duration INTEGER DEFAULT 60, -- Minutes
    actual_duration INTEGER,
    distance_miles DECIMAL(8,2),
    vehicle_type VARCHAR(50) NOT NULL,
    customer_name VARCHAR(200) NOT NULL,
    customer_email VARCHAR(255) NOT NULL,
    customer_phone VARCHAR(20) NOT NULL,
    passenger_count INTEGER DEFAULT 1,
    special_requests TEXT, -- Frontend: special_instructions -> Schema: special_requests
    base_price DECIMAL(10,2) NOT NULL,
    surge_multiplier DECIMAL(3,2) DEFAULT 1.00,
    discount_amount DECIMAL(10,2) DEFAULT 0.00,
    tax_amount DECIMAL(10,2) DEFAULT 0.00,
    tip_amount DECIMAL(10,2) DEFAULT 0.00,
    total_amount DECIMAL(10,2) NOT NULL,
    status booking_status DEFAULT 'pending',
    payment_status payment_status DEFAULT 'pending',
    confirmation_code VARCHAR(20),
    pickup_location POINT,
    destination_location POINT,
    route_info JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Payments table with consistent ID format
CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    payment_id VARCHAR(20) UNIQUE NOT NULL, -- PAY20241201ABC123
    booking_id UUID REFERENCES bookings(id) NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    payment_method VARCHAR(50) NOT NULL,
    payment_status payment_status DEFAULT 'pending',
    transaction_id VARCHAR(255), -- Stripe payment intent ID
    gateway_transaction_id VARCHAR(255), -- Gateway-specific transaction ID
    gateway_name VARCHAR(50) DEFAULT 'stripe',
    gateway_response JSONB,
    processed_at TIMESTAMP WITH TIME ZONE,
    refunded_at TIMESTAMP WITH TIME ZONE,
    refund_amount DECIMAL(10,2) DEFAULT 0.00,
    description TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Admin users table with role-based access
CREATE TABLE admin_users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    role VARCHAR(50) DEFAULT 'admin', -- admin, super_admin
    department VARCHAR(100),
    phone VARCHAR(20),
    status account_status DEFAULT 'active',
    last_login TIMESTAMP WITH TIME ZONE,
    permissions JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- System settings table for database-driven configuration
CREATE TABLE system_settings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    setting_key VARCHAR(100) UNIQUE NOT NULL,
    setting_value TEXT NOT NULL,
    setting_type VARCHAR(20) DEFAULT 'string', -- string, number, boolean, json
    category VARCHAR(50) DEFAULT 'general',
    description TEXT,
    is_public BOOLEAN DEFAULT FALSE,
    updated_by UUID REFERENCES admin_users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Audit logs table for comprehensive tracking
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255) NOT NULL, -- Can be email or UUID
    user_type VARCHAR(50) NOT NULL, -- customer, driver, admin
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id VARCHAR(255),
    details JSONB DEFAULT '{}',
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Enhanced notifications table with retry logic
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    recipient_id VARCHAR(255) NOT NULL, -- Can be email or UUID
    recipient_type VARCHAR(50) NOT NULL, -- customer, driver, admin
    type VARCHAR(100) NOT NULL, -- booking_confirmation, payment_confirmation, etc.
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    status notification_status DEFAULT 'pending',
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    email_sent BOOLEAN DEFAULT FALSE,
    sms_sent BOOLEAN DEFAULT FALSE,
    push_sent BOOLEAN DEFAULT FALSE,
    sent_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Ratings table for feedback system
CREATE TABLE ratings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    booking_id UUID REFERENCES bookings(id) NOT NULL,
    user_id UUID REFERENCES users(id),
    driver_id UUID REFERENCES drivers(id),
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    review TEXT,
    service_quality INTEGER CHECK (service_quality >= 1 AND service_quality <= 5),
    punctuality INTEGER CHECK (punctuality >= 1 AND punctuality <= 5),
    vehicle_condition INTEGER CHECK (vehicle_condition >= 1 AND vehicle_condition <= 5),
    driver_professionalism INTEGER CHECK (driver_professionalism >= 1 AND driver_professionalism <= 5),
    would_recommend BOOLEAN,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Vehicle assignments table for tracking driver-vehicle relationships
CREATE TABLE vehicle_assignments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    driver_id UUID REFERENCES drivers(id) NOT NULL,
    vehicle_id UUID REFERENCES vehicles(id) NOT NULL,
    assigned_date DATE NOT NULL,
    unassigned_date DATE,
    is_active BOOLEAN DEFAULT TRUE,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX idx_bookings_customer_email ON bookings(customer_email);
CREATE INDEX idx_bookings_driver_id ON bookings(driver_id);
CREATE INDEX idx_bookings_pickup_date ON bookings(pickup_date);
CREATE INDEX idx_bookings_status ON bookings(status);
CREATE INDEX idx_bookings_payment_status ON bookings(payment_status);
CREATE INDEX idx_payments_booking_id ON payments(booking_id);
CREATE INDEX idx_payments_transaction_id ON payments(transaction_id);
CREATE INDEX idx_payments_status ON payments(payment_status);
CREATE INDEX idx_drivers_status ON drivers(status);
CREATE INDEX idx_drivers_employment_status ON drivers(employment_status);
CREATE INDEX idx_vehicles_status ON vehicles(status);
CREATE INDEX idx_vehicles_type ON vehicles(vehicle_type);
CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_action ON audit_logs(action);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at);
CREATE INDEX idx_notifications_recipient_id ON notifications(recipient_id);
CREATE INDEX idx_notifications_status ON notifications(status);
CREATE INDEX idx_notifications_retry_count ON notifications(retry_count);
CREATE INDEX idx_system_settings_key ON system_settings(setting_key);
CREATE INDEX idx_system_settings_category ON system_settings(category);

-- Row Level Security (RLS) policies
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE drivers ENABLE ROW LEVEL SECURITY;
ALTER TABLE bookings ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;

-- RLS Policies for users table
CREATE POLICY "Users can view own data" ON users
    FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Users can update own data" ON users
    FOR UPDATE USING (auth.uid() = id);

-- RLS Policies for drivers table
CREATE POLICY "Drivers can view own data" ON drivers
    FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Drivers can update own data" ON drivers
    FOR UPDATE USING (auth.uid() = id);

CREATE POLICY "Admins can view all drivers" ON drivers
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM admin_users 
            WHERE id = auth.uid() AND status = 'active'
        )
    );

-- RLS Policies for bookings table
CREATE POLICY "Users can view own bookings" ON bookings
    FOR SELECT USING (user_id = auth.uid() OR customer_email = auth.email());

CREATE POLICY "Drivers can view assigned bookings" ON bookings
    FOR SELECT USING (driver_id = auth.uid());

CREATE POLICY "Admins can view all bookings" ON bookings
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM admin_users 
            WHERE id = auth.uid() AND status = 'active'
        )
    );

-- RLS Policies for payments table
CREATE POLICY "Users can view own payments" ON payments
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM bookings 
            WHERE bookings.id = payments.booking_id 
            AND (bookings.user_id = auth.uid() OR bookings.customer_email = auth.email())
        )
    );

CREATE POLICY "Admins can view all payments" ON payments
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM admin_users 
            WHERE id = auth.uid() AND status = 'active'
        )
    );

-- Insert default system settings for pricing
INSERT INTO system_settings (setting_key, setting_value, setting_type, category, description) VALUES
('executive_sedan_base_rate', '25.00', 'number', 'pricing', 'Base rate for executive sedan'),
('executive_sedan_hourly_rate', '65.00', 'number', 'pricing', 'Hourly rate for executive sedan'),
('executive_sedan_airport_rate', '75.00', 'number', 'pricing', 'Airport transfer rate for executive sedan'),
('luxury_suv_base_rate', '35.00', 'number', 'pricing', 'Base rate for luxury SUV'),
('luxury_suv_hourly_rate', '95.00', 'number', 'pricing', 'Hourly rate for luxury SUV'),
('luxury_suv_airport_rate', '105.00', 'number', 'pricing', 'Airport transfer rate for luxury SUV'),
('sprinter_van_base_rate', '45.00', 'number', 'pricing', 'Base rate for sprinter van'),
('sprinter_van_hourly_rate', '120.00', 'number', 'pricing', 'Hourly rate for sprinter van'),
('sprinter_van_airport_rate', '130.00', 'number', 'pricing', 'Airport transfer rate for sprinter van'),
('default_tax_rate', '8.25', 'number', 'pricing', 'Default tax rate percentage'),
('surge_pricing_enabled', 'false', 'boolean', 'pricing', 'Enable surge pricing during peak hours'),
('booking_advance_hours', '2', 'number', 'booking', 'Minimum hours in advance for booking'),
('cancellation_fee', '25.00', 'number', 'booking', 'Cancellation fee amount'),
('company_name', 'BLuxA Corp', 'string', 'general', 'Company name'),
('company_phone', '+1-555-BLUXA-1', 'string', 'general', 'Company phone number'),
('company_email', 'info@bluxacorp.com', 'string', 'general', 'Company email address'),
('support_email', 'support@bluxacorp.com', 'string', 'general', 'Support email address'),
('notification_email_enabled', 'true', 'boolean', 'notifications', 'Enable email notifications'),
('notification_sms_enabled', 'true', 'boolean', 'notifications', 'Enable SMS notifications'),
('driver_commission_rate', '80.00', 'number', 'driver', 'Default driver commission percentage');

-- Insert sample vehicles with pricing
INSERT INTO vehicles (vehicle_id, make, model, year, color, license_plate, vin, vehicle_type, passenger_capacity, base_rate, per_hour_rate, airport_surcharge, minimum_charge) VALUES
('VEH001', 'Mercedes-Benz', 'S-Class', 2023, 'Black', 'BLX-001', '1HGBH41JXMN109186', 'executive_sedan', 4, 25.00, 65.00, 10.00, 50.00),
('VEH002', 'BMW', '7 Series', 2023, 'Silver', 'BLX-002', '1HGBH41JXMN109187', 'executive_sedan', 4, 25.00, 65.00, 10.00, 50.00),
('VEH003', 'Cadillac', 'Escalade', 2023, 'Black', 'BLX-003', '1HGBH41JXMN109188', 'luxury_suv', 7, 35.00, 95.00, 15.00, 70.00),
('VEH004', 'Lincoln', 'Navigator', 2023, 'White', 'BLX-004', '1HGBH41JXMN109189', 'luxury_suv', 7, 35.00, 95.00, 15.00, 70.00),
('VEH005', 'Mercedes-Benz', 'Sprinter', 2023, 'Black', 'BLX-005', '1HGBH41JXMN109190', 'sprinter_van', 12, 45.00, 120.00, 20.00, 90.00);

-- Create functions for automatic updates
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for updated_at columns
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_drivers_updated_at BEFORE UPDATE ON drivers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_vehicles_updated_at BEFORE UPDATE ON vehicles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_bookings_updated_at BEFORE UPDATE ON bookings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_payments_updated_at BEFORE UPDATE ON payments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_admin_users_updated_at BEFORE UPDATE ON admin_users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_system_settings_updated_at BEFORE UPDATE ON system_settings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_notifications_updated_at BEFORE UPDATE ON notifications
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_vehicle_assignments_updated_at BEFORE UPDATE ON vehicle_assignments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create function to update driver stats
CREATE OR REPLACE FUNCTION update_driver_stats()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'completed' AND OLD.status != 'completed' THEN
        UPDATE drivers 
        SET total_rides = total_rides + 1,
            total_earnings = total_earnings + (NEW.total_amount * commission_rate / 100)
        WHERE id = NEW.driver_id;
    END IF;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_driver_stats_trigger AFTER UPDATE ON bookings
    FOR EACH ROW EXECUTE FUNCTION update_driver_stats();

-- Comments for documentation
COMMENT ON TABLE users IS 'Customer user accounts - Supabase Auth is source of truth for authentication';
COMMENT ON TABLE drivers IS 'Driver profiles with employment and performance data';
COMMENT ON TABLE vehicles IS 'Fleet vehicles with database-driven pricing configuration';
COMMENT ON TABLE bookings IS 'Transportation bookings with separate pickup_date and pickup_time fields';
COMMENT ON TABLE payments IS 'Payment records with Stripe integration and consistent ID format';
COMMENT ON TABLE admin_users IS 'Administrative user accounts with role-based access';
COMMENT ON TABLE system_settings IS 'System configuration settings stored in database';
COMMENT ON TABLE audit_logs IS 'Comprehensive audit trail for all system actions';
COMMENT ON TABLE notifications IS 'Notification system with retry logic and status tracking';
COMMENT ON TABLE ratings IS 'Customer feedback and rating system';
COMMENT ON TABLE vehicle_assignments IS 'Driver-vehicle assignment tracking';

COMMENT ON COLUMN bookings.pickup_date IS 'Separate pickup date field as requested';
COMMENT ON COLUMN bookings.pickup_time IS 'Separate pickup time field as requested';
COMMENT ON COLUMN bookings.special_requests IS 'Maps to frontend special_instructions field';
COMMENT ON COLUMN vehicles.base_rate IS 'Database-driven pricing - base rate';
COMMENT ON COLUMN vehicles.per_hour_rate IS 'Database-driven pricing - hourly rate';
COMMENT ON COLUMN vehicles.airport_surcharge IS 'Database-driven pricing - airport surcharge';
COMMENT ON COLUMN notifications.retry_count IS 'Current retry attempt count for failed notifications';
COMMENT ON COLUMN notifications.max_retries IS 'Maximum retry attempts before giving up';
