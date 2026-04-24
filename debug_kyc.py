#!/usr/bin/env python3
"""
Debug KYC OCR Issues
"""

import requests
import json
import io
from PIL import Image, ImageDraw, ImageFont

def create_test_aadhaar_image():
    """Create a simple test Aadhaar image"""
    # Create a simple image with text
    img = Image.new('RGB', (400, 250), color='white')
    draw = ImageDraw.Draw(img)
    
    # Try to use a simple font
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except:
        font = ImageFont.load_default()
    
    # Draw Aadhaar-like text
    draw.text((20, 20), "GOVERNMENT OF INDIA", fill='black', font=font)
    draw.text((20, 50), "UNIQUE IDENTIFICATION AUTHORITY", fill='black', font=font)
    draw.text((20, 80), "Test Name", fill='black', font=font)
    draw.text((20, 110), "DOB: 15/01/1990", fill='black', font=font)
    draw.text((20, 140), "1234 5678 9012", fill='black', font=font)
    draw.text((20, 170), "Male", fill='black', font=font)
    
    # Convert to bytes
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    
    return img_bytes.getvalue()

def test_aadhaar_extraction():
    """Test Aadhaar extraction with debug info"""
    print("🔍 Testing Aadhaar Extraction...")
    
    # Create test image
    test_image = create_test_aadhaar_image()
    
    # Test the endpoint
    url = "http://localhost:8003/kyc/extract/aadhaar"
    
    files = {
        'document': ('test_aadhaar.png', test_image, 'image/png'),
        'language': 'en'
    }
    
    try:
        print("📤 Sending request to KYC service...")
        response = requests.post(url, files=files, timeout=30)
        
        print(f"📊 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Success! Extracted data:")
            print(json.dumps(result, indent=2))
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.Timeout:
        print("❌ Request timed out")
    except requests.exceptions.ConnectionError:
        print("❌ Connection error - is KYC service running?")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

def test_health():
    """Test service health"""
    print("🔍 Testing KYC Service Health...")
    
    try:
        response = requests.get("http://localhost:8003/health", timeout=10)
        
        if response.status_code == 200:
            health = response.json()
            print("✅ KYC Service is healthy")
            print(f"Status: {health['status']}")
            print(f"Uptime: {health['uptime_seconds']}s")
        else:
            print(f"❌ Health check failed: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Health check error: {e}")

def main():
    print("🐛 KYC OCR Debug Tool")
    print("=" * 50)
    
    # Test health first
    test_health()
    print()
    
    # Test Aadhaar extraction
    test_aadhaar_extraction()

if __name__ == "__main__":
    main()
