#!/usr/bin/env python3
"""
Debug script to test PAN upload functionality
"""

import requests
import json
import io
from PIL import Image
import numpy as np

BASE_URL = "http://localhost:8000"

def create_test_image():
    """Create a simple test image"""
    # Create a simple test image with text
    img = Image.new('RGB', (400, 200), color='white')
    
    # This is just a test - real PAN cards would have actual PAN numbers
    return img

def test_pan_upload():
    print("🔍 Testing PAN Upload Functionality")
    print("=" * 50)
    
    # Create a simple test image
    test_img = create_test_image()
    
    # Convert to bytes
    img_bytes = io.BytesIO()
    test_img.save(img_bytes, format='JPEG')
    img_bytes.seek(0)
    
    # Test the upload
    try:
        files = {
            'document': ('test_pan.jpg', img_bytes.getvalue(), 'image/jpeg')
        }
        data = {
            'session_id': 'test_session_debug',
            'language': 'en'
        }
        
        print("📤 Sending test PAN image...")
        response = requests.post(f"{BASE_URL}/kyc/extract/pan", files=files, data=data)
        
        print(f"📊 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Success! PAN extraction worked:")
            print(f"   - Document Type: {result.get('document_type')}")
            print(f"   - Confidence: {result.get('confidence_score')}")
            print(f"   - Processing Time: {result.get('processing_time_ms')}ms")
            
            validation = result.get('validation', {})
            print(f"   - PAN Valid: {validation.get('pan_format_valid')}")
            print(f"   - Overall Valid: {validation.get('overall_valid')}")
            print(f"   - Issues: {validation.get('issues', [])}")
            
            extracted = result.get('extracted_fields', {})
            if extracted.get('pan_number'):
                print(f"   - PAN Number: {extracted['pan_number']}")
            if extracted.get('name'):
                print(f"   - Name: {extracted['name']}")
                
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"   - Detail: {response.text}")
            
    except Exception as e:
        print(f"❌ Exception: {e}")

def test_backend_health():
    print("\n🏥 Testing Backend Health")
    print("=" * 30)
    
    try:
        response = requests.get(f"{BASE_URL}/kyc/health")
        if response.status_code == 200:
            health = response.json()
            print("✅ KYC Service Health:")
            print(f"   - Status: {health.get('status')}")
            print(f"   - OCR Ready: {health.get('ocr_ready')}")
            print(f"   - Max Upload: {health.get('max_upload_mb')}MB")
        else:
            print(f"❌ Health check failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Health check error: {e}")

if __name__ == "__main__":
    test_backend_health()
    test_pan_upload()
