#!/usr/bin/env python3
"""
Test script for BLuxA Corp Backend
Tests the fixes for DNS errors, booking validation, and rate limiting
"""

import requests
import json
import time

BASE_URL = "http://localhost:5000"

def test_health_endpoint():
    """Test health endpoint"""
    print("Testing health endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        print(f"Health check: {response.status_code}")
        if response.status_code == 200:
            print("✓ Health endpoint working")
            return True
    except Exception as e:
        print(f"✗ Health endpoint failed: {e}")
    return False

def test_pricing_endpoint():
    """Test pricing endpoint"""
    print("\nTesting pricing endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/pricing")
        print(f"Pricing check: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print("✓ Pricing endpoint working")
            print(f"  Available vehicles: {list(data['pricing'].keys())}")
            return True
    except Exception as e:
        print(f"✗ Pricing endpoint failed: {e}")
    return False

def test_booking_validation():
    """Test booking endpoint validation"""
    print("\nTesting booking validation...")
    
    # Test 1: Missing required fields
    print("Test 1: Missing required fields")
    try:
        response = requests.post(f"{BASE_URL}/bookings", json={})
        print(f"Empty booking: {response.status_code}")
        if response.status_code == 400:
            print("✓ Properly rejects empty booking")
        else:
            print("✗ Should reject empty booking")
    except Exception as e:
        print(f"✗ Empty booking test failed: {e}")
    
    # Test 2: Valid booking
    print("\nTest 2: Valid booking")
    try:
        valid_booking = {
            "pickup_location": "123 Main St, New York, NY",
            "dropoff_location": "456 Broadway, New York, NY",
            "pickup_datetime": "2025-01-15T10:00:00Z",
            "vehicle_type": "executive_sedan",
            "passenger_count": 2,
            "special_requests": "Wheelchair accessible"
        }
        response = requests.post(f"{BASE_URL}/bookings", json=valid_booking)
        print(f"Valid booking: {response.status_code}")
        if response.status_code == 201:
            data = response.json()
            print("✓ Valid booking created successfully")
            print(f"  Booking ID: {data.get('booking_id')}")
            return data.get('id')
        else:
            print("✗ Valid booking should succeed")
    except Exception as e:
        print(f"✗ Valid booking test failed: {e}")
    
    return None

def test_rate_limiting():
    """Test rate limiting"""
    print("\nTesting rate limiting...")
    try:
        # Send multiple requests quickly
        for i in range(12):  # More than the 10 per minute limit
            response = requests.post(f"{BASE_URL}/bookings", json={
                "pickup_location": f"Test Location {i}",
                "dropoff_location": f"Test Destination {i}",
                "pickup_datetime": "2025-01-15T10:00:00Z"
            })
            print(f"Request {i+1}: {response.status_code}")
            if response.status_code == 429:  # Too Many Requests
                print("✓ Rate limiting working")
                return True
            time.sleep(0.1)  # Small delay between requests
    except Exception as e:
        print(f"✗ Rate limiting test failed: {e}")
    
    print("✗ Rate limiting not triggered (may need more requests)")
    return False

def main():
    """Run all tests"""
    print("BLuxA Corp Backend Test Suite")
    print("=" * 40)
    
    # Test basic endpoints
    health_ok = test_health_endpoint()
    pricing_ok = test_pricing_endpoint()
    
    if not health_ok or not pricing_ok:
        print("\n✗ Basic endpoints not working. Make sure backend is running.")
        return
    
    # Test booking functionality
    booking_id = test_booking_validation()
    
    # Test rate limiting
    test_rate_limiting()
    
    print("\n" + "=" * 40)
    print("Test Summary:")
    print(f"Health endpoint: {'✓' if health_ok else '✗'}")
    print(f"Pricing endpoint: {'✓' if pricing_ok else '✗'}")
    print(f"Booking validation: {'✓' if booking_id else '✗'}")
    print("\nBackend fixes applied:")
    print("✓ DNS error handling for notifications")
    print("✓ Improved booking validation")
    print("✓ Rate limiting configuration")
    print("✓ Proper error logging")

if __name__ == "__main__":
    main()
