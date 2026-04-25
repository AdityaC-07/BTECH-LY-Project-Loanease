#!/usr/bin/env python3
"""
Test real PDF upload with detailed logging
"""

import requests
import json

BASE_URL = "http://localhost:8000"

def test_pdf_upload():
    print("📄 Testing Real PDF Upload")
    print("=" * 30)
    
    # Create a simple PDF-like content to test processing
    fake_pdf_content = b'%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n/Contents 4 0 R\n>>\nendobj\n4 0 obj\n<<\n/Length 44\n>>\nstream\nBT\n/F1 12 Tf\n72 720 Td\n(PAN CARD) Tj\nET\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000204 00000 n \ntrailer\n<<\n/Size 5\n/Root 1 0 R\n>>\nstartxref\n312\n%%EOF'
    
    try:
        files = {
            'document': ('test_pan.pdf', fake_pdf_content, 'application/pdf')
        }
        data = {
            'session_id': 'test_real_pdf',
            'language': 'en'
        }
        
        print("📤 Sending real PDF content...")
        response = requests.post(f"{BASE_URL}/kyc/extract/pan", files=files, data=data)
        
        print(f"📊 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ PDF processing worked!")
            print(f"   - Document Type: {result.get('document_type')}")
            print(f"   - Confidence: {result.get('confidence_score')}")
            print(f"   - Processing Time: {result.get('processing_time_ms')}ms")
            
            validation = result.get('validation', {})
            print(f"   - PAN Valid: {validation.get('pan_format_valid')}")
            print(f"   - Overall Valid: {validation.get('overall_valid')}")
            print(f"   - Issues: {validation.get('issues', [])}")
            
        else:
            print(f"❌ Error: {response.status_code}")
            result = response.json()
            error_detail = result.get('detail', 'Unknown error')
            print(f"   - Error: {error_detail}")
            
            # Check if it's a PDF processing error
            if 'pdf' in error_detail.lower():
                print("   - PDF-specific error detected")
            elif 'file' in error_detail.lower():
                print("   - File processing error detected")
            else:
                print("   - General processing error")
                
    except Exception as e:
        print(f"❌ Exception: {e}")

def test_image_upload():
    print("\n🖼️ Testing Image Upload for Comparison")
    print("=" * 40)
    
    # Create a simple test image
    from PIL import Image
    import io
    
    img = Image.new('RGB', (400, 200), color='white')
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='JPEG')
    img_bytes.seek(0)
    
    try:
        files = {
            'document': ('test_pan.jpg', img_bytes.getvalue(), 'image/jpeg')
        }
        data = {
            'session_id': 'test_real_image',
            'language': 'en'
        }
        
        print("📤 Sending test image...")
        response = requests.post(f"{BASE_URL}/kyc/extract/pan", files=files, data=data)
        
        print(f"📊 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Image processing worked!")
            print(f"   - Document Type: {result.get('document_type')}")
            print(f"   - Confidence: {result.get('confidence_score')}")
        else:
            print(f"❌ Image Error: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Image Exception: {e}")

if __name__ == "__main__":
    test_pdf_upload()
    test_image_upload()
