-- Enhanced Schema Additions for BLuxA Corp Production System
-- Add missing columns for driver dashboard and notification improvements

-- Add rating and total_rides columns to drivers table if they don't exist
ALTER TABLE drivers 
ADD COLUMN IF NOT EXISTS rating DECIMAL(3,2) DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS total_rides INTEGER DEFAULT 0;

-- Add comment for clarity
COMMENT ON COLUMN drivers.rating IS 'Driver average rating from 0.0 to 5.0';
COMMENT ON COLUMN drivers.total_rides IS 'Total number of completed rides by driver';

-- Create index for better performance on rating queries
CREATE INDEX IF NOT EXISTS idx_drivers_rating ON drivers(rating);
CREATE INDEX IF NOT EXISTS idx_drivers_total_rides ON drivers(total_rides);

-- Update existing drivers to have default values if needed
UPDATE drivers 
SET rating = 0.0 
WHERE rating IS NULL;

UPDATE drivers 
SET total_rides = 0 
WHERE total_rides IS NULL;

-- Add constraints to ensure data integrity
ALTER TABLE drivers 
ADD CONSTRAINT IF NOT EXISTS chk_rating_range 
CHECK (rating >= 0.0 AND rating <= 5.0);

ALTER TABLE drivers 
ADD CONSTRAINT IF NOT EXISTS chk_total_rides_positive 
CHECK (total_rides >= 0);

-- Enhanced notification retry improvements
-- Add index for better performance on notification retry queries
CREATE INDEX IF NOT EXISTS idx_notifications_status_retry ON notifications(status, retry_count);
CREATE INDEX IF NOT EXISTS idx_notifications_pending_created ON notifications(status, created_at) 
WHERE status = 'pending';

-- Add index for failed notifications that haven't exceeded max retries
CREATE INDEX IF NOT EXISTS idx_notifications_failed_retryable ON notifications(status, retry_count, max_retries) 
WHERE status = 'failed' AND retry_count < max_retries;

-- Update notification table comment
COMMENT ON TABLE notifications IS 'System notifications with enhanced retry logic for failed deliveries';

-- Ensure proper RLS policies for new columns
-- (These would be applied if RLS is enabled)

-- Policy for drivers to read their own rating and total_rides
DROP POLICY IF EXISTS "Drivers can view own rating and stats" ON drivers;
CREATE POLICY "Drivers can view own rating and stats" ON drivers
    FOR SELECT USING (auth.uid() = id);

-- Policy for admins to update driver ratings and stats
DROP POLICY IF EXISTS "Admins can update driver stats" ON drivers;
CREATE POLICY "Admins can update driver stats" ON drivers
    FOR UPDATE USING (
        EXISTS (
            SELECT 1 FROM admin_users 
            WHERE id = auth.uid() AND status = 'active'
        )
    );

-- Add helpful views for admin dashboard
CREATE OR REPLACE VIEW driver_performance_summary AS
SELECT 
    d.id,
    d.driver_id,
    d.first_name,
    d.last_name,
    d.rating,
    d.total_rides,
    d.employment_status,
    d.account_status,
    COUNT(b.id) as current_month_rides,
    COALESCE(SUM(b.total_amount), 0) as current_month_revenue
FROM drivers d
LEFT JOIN bookings b ON d.id = b.driver_id 
    AND b.pickup_date >= date_trunc('month', CURRENT_DATE)
    AND b.status = 'completed'
GROUP BY d.id, d.driver_id, d.first_name, d.last_name, d.rating, d.total_rides, d.employment_status, d.account_status;

-- Add helpful view for notification monitoring
CREATE OR REPLACE VIEW notification_status_summary AS
SELECT 
    status,
    COUNT(*) as count,
    AVG(retry_count) as avg_retry_count,
    MAX(retry_count) as max_retry_count,
    COUNT(*) FILTER (WHERE retry_count >= max_retries) as exceeded_max_retries
FROM notifications
GROUP BY status;

-- Grant appropriate permissions
GRANT SELECT ON driver_performance_summary TO authenticated;
GRANT SELECT ON notification_status_summary TO authenticated;

-- Add helpful function for calculating driver ratings
CREATE OR REPLACE FUNCTION update_driver_rating(driver_uuid UUID, new_rating DECIMAL)
RETURNS VOID AS $$
BEGIN
    -- Update driver rating and increment total_rides if rating is for completed ride
    UPDATE drivers 
    SET 
        rating = CASE 
            WHEN total_rides = 0 THEN new_rating
            ELSE ((rating * total_rides) + new_rating) / (total_rides + 1)
        END,
        total_rides = total_rides + 1
    WHERE id = driver_uuid;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Add function to clean up old notifications (for maintenance)
CREATE OR REPLACE FUNCTION cleanup_old_notifications(days_old INTEGER DEFAULT 30)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM notifications 
    WHERE created_at < (CURRENT_DATE - INTERVAL '1 day' * days_old)
    AND status IN ('sent', 'failed');
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Add helpful triggers for automatic updates
CREATE OR REPLACE FUNCTION update_driver_total_rides()
RETURNS TRIGGER AS $$
BEGIN
    -- Automatically update driver total_rides when booking is completed
    IF NEW.status = 'completed' AND OLD.status != 'completed' AND NEW.driver_id IS NOT NULL THEN
        UPDATE drivers 
        SET total_rides = total_rides + 1
        WHERE id = NEW.driver_id;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for automatic total_rides updates
DROP TRIGGER IF EXISTS trigger_update_driver_total_rides ON bookings;
CREATE TRIGGER trigger_update_driver_total_rides
    AFTER UPDATE ON bookings
    FOR EACH ROW
    EXECUTE FUNCTION update_driver_total_rides();

-- Add indexes for better performance on admin queries
CREATE INDEX IF NOT EXISTS idx_bookings_driver_status ON bookings(driver_id, status);
CREATE INDEX IF NOT EXISTS idx_bookings_pickup_date_status ON bookings(pickup_date, status);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_action ON audit_logs(user_id, action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);

-- Final verification queries (these can be run to verify the schema)
-- SELECT column_name, data_type, is_nullable, column_default 
-- FROM information_schema.columns 
-- WHERE table_name = 'drivers' AND column_name IN ('rating', 'total_rides');

-- SELECT indexname, indexdef 
-- FROM pg_indexes 
-- WHERE tablename IN ('drivers', 'notifications', 'bookings', 'audit_logs')
-- ORDER BY tablename, indexname;
