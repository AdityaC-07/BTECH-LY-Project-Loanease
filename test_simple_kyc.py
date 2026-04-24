#!/usr/bin/env python3
"""
Simple KYC test to isolate the issue
"""

import requests
import json

def test_endpoints():
    """Test what endpoints are actually available"""
    print("🔍 Testing available endpoints...")
    
    # Test health on port 8004 (KYC)
    try:
        response = requests.get("http://localhost:8004/health")
        print(f"KYC Health (8004): {response.status_code}")
        if response.status_code == 200:
            print(f"KYC Health data: {response.json()}")
    except Exception as e:
        print(f"KYC Health error: {e}")
    
    # Test docs
    try:
        response = requests.get("http://localhost:8004/docs")
        print(f"KYC Docs: {response.status_code}")
    except Exception as e:
        print(f"KYC Docs error: {e}")
    
    # Test openapi
    try:
        response = requests.get("http://localhost:8004/openapi.json")
        print(f"KYC OpenAPI: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            paths = data.get("paths", {})
            print(f"KYC Available paths: {list(paths.keys())}")
    except Exception as e:
        print(f"KYC OpenAPI error: {e}")

def test_direct_kyc():
    """Test direct KYC endpoint with POST"""
    print("\n🔍 Testing direct KYC endpoint...")
    
    url = "http://localhost:8004/kyc/extract/aadhaar"
    
    # Try with empty request to see if endpoint exists
    try:
        response = requests.post(url, timeout=5)
        print(f"Direct POST to {url}: {response.status_code}")
        print(f"Response: {response.text}")
    except requests.exceptions.ConnectTimeout:
        print("Connection timeout")
    except requests.exceptions.ReadTimeout:
        print("Read timeout")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_endpoints()
    test_direct_kyc()
