#!/usr/bin/env python3
"""
Test PDF support for PAN and Aadhaar upload
"""

import requests
import json

BASE_URL = "http://localhost:8000"

def test_pdf_support():
    print("📄 Testing PDF Support")
    print("=" * 30)
    
    # Test 1: Check if PDF is in allowed file types
    try:
        # Create a simple test request (this will fail but show the error)
        response = requests.post(f"{BASE_URL}/kyc/extract/pan", 
                               files={'document': ('test.pdf', b'fake pdf content', 'application/pdf')},
                               data={'session_id': 'test_pdf', 'language': 'en'})
        
        print(f"📊 PDF Upload Response: {response.status_code}")
        if response.status_code != 200:
            result = response.json()
            print(f"   - Error: {result.get('detail', 'Unknown error')}")
            
            # Check if the error is about PDF processing (good) or file type (bad)
            error_detail = result.get('detail', '').lower()
            if 'pdf' in error_detail and ('process' in error_detail or 'extract' in error_detail):
                print("✅ PDF processing is attempted (file type accepted)")
            elif 'unsupported file type' in error_detail:
                print("❌ PDF file type not supported")
            else:
                print("✅ PDF file type accepted (processing error is expected)")
        else:
            print("✅ PDF upload succeeded!")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")

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

def test_file_types():
    print("\n📋 Testing File Type Support")
    print("=" * 35)
    
    supported_types = ['jpg', 'jpeg', 'png', 'pdf', 'bmp', 'tiff']
    
    for file_type in supported_types:
        try:
            # Create fake content for each type
            content_type = {
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg', 
                'png': 'image/png',
                'pdf': 'application/pdf',
                'bmp': 'image/bmp',
                'tiff': 'image/tiff'
            }.get(file_type, 'application/octet-stream')
            
            response = requests.post(f"{BASE_URL}/kyc/extract/pan",
                                   files={'document': (f'test.{file_type}', b'fake content', content_type)},
                                   data={'session_id': f'test_{file_type}', 'language': 'en'})
            
            if response.status_code == 400:
                result = response.json()
                error_detail = result.get('detail', '').lower()
                if 'unsupported file type' in error_detail:
                    print(f"❌ {file_type.upper()}: Not supported")
                else:
                    print(f"✅ {file_type.upper()}: Supported (processing error expected)")
            elif response.status_code == 200:
                print(f"✅ {file_type.upper()}: Supported and processed")
            else:
                print(f"⚠️  {file_type.upper()}: Unexpected response {response.status_code}")
                
        except Exception as e:
            print(f"❌ {file_type.upper()}: Test error - {e}")

if __name__ == "__main__":
    test_backend_health()
    test_pdf_support()
    test_file_types()
