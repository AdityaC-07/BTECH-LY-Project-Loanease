#!/usr/bin/env python3
"""
Test KYC verification endpoint
"""

import requests
import io
from PIL import Image, ImageDraw, ImageFont

def create_test_pan_image():
    """Create a simple test PAN image"""
    img = Image.new('RGB', (400, 250), color='white')
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except:
        font = ImageFont.load_default()
    
    draw.text((20, 20), "INCOME TAX DEPARTMENT", fill='black', font=font)
    draw.text((20, 50), "Test User", fill='black', font=font)
    draw.text((20, 80), "ABCDE1234F", fill='black', font=font)
    draw.text((20, 110), "DOB: 15/01/1990", fill='black', font=font)
    
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    
    return img_bytes.getvalue()

def create_test_aadhaar_image():
    """Create a simple test Aadhaar image"""
    img = Image.new('RGB', (400, 250), color='white')
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except:
        font = ImageFont.load_default()
    
    draw.text((20, 20), "GOVERNMENT OF INDIA", fill='black', font=font)
    draw.text((20, 50), "Test User", fill='black', font=font)
    draw.text((20, 80), "DOB: 15/01/1990", fill='black', font=font)
    draw.text((20, 110), "1234 5678 9012", fill='black', font=font)
    draw.text((20, 140), "Male", fill='black', font=font)
    
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    
    return img_bytes.getvalue()

def test_kyc_verification():
    """Test KYC verification endpoint"""
    print("🔍 Testing KYC Verification Endpoint...")
    
    # Create test documents
    pan_image = create_test_pan_image()
    aadhaar_image = create_test_aadhaar_image()
    
    # Test the verification endpoint
    url = "http://localhost:8004/kyc/verify"
    
    files = {
        'pan': ('test_pan.png', pan_image, 'image/png'),
        'aadhaar': ('test_aadhaar.png', aadhaar_image, 'image/png')
    }
    
    try:
        print("📤 Sending verification request...")
        response = requests.post(url, files=files, timeout=60)
        
        print(f"📊 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Verification successful!")
            print(f"KYC Status: {result.get('kyc_status')}")
            print(f"Overall Passed: {result.get('overall_kyc_passed')}")
            print(f"Name Match Score: {result.get('cross_validation', {}).get('name_match_score')}")
            print(f"Reference ID: {result.get('kyc_reference_id')}")
            return True
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ Request timed out")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ Connection error")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def main():
    print("🐛 KYC Verification Test")
    print("=" * 50)
    
    success = test_kyc_verification()
    
    if success:
        print("\n✅ KYC verification endpoint is working!")
    else:
        print("\n❌ KYC verification endpoint has issues")

if __name__ == "__main__":
    main()
