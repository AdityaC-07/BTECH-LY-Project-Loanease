import sys
from pathlib import Path

# Add app to path
sys.path.append(str(Path(__file__).parent.parent))

from app.enhanced_service import EnhancedKYCService
from app.enhanced_preprocess import assess_image_quality
import numpy as np
import cv2

def test_image_quality():
    print("Testing Image Quality Assessment...")
    # Create a dummy image (small and blurry)
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    quality = assess_image_quality(img)
    print(f"Poor Quality Score: {quality['quality_score']}")
    print(f"Issues: {quality['issues']}")
    assert quality['proceed'] is False
    
    # Create a "good" dummy image
    img_good = np.ones((800, 1200, 3), dtype=np.uint8) * 128
    # Add some "text" to avoid zero variance
    cv2.putText(img_good, "TEST DOCUMENT", (100, 100), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 2)
    quality_good = assess_image_quality(img_good)
    print(f"Good Quality Score: {quality_good['quality_score']}")
    print(f"Proceed: {quality_good['proceed']}")

def test_field_confidence():
    from app.enhanced_extractors import score_field_confidence
    print("\nTesting Field Confidence Scoring...")
    
    pan_conf = score_field_confidence("PAN: ABCDE1234F", "ABCDE1234F", "pan")
    print(f"PAN Confidence: {pan_conf}")
    
    name_conf = score_field_confidence("NAME: JOHN DOE", "JOHN DOE", "name")
    print(f"Name Confidence: {name_conf}")
    
    dob_conf = score_field_confidence("DOB: 01/01/1990", "01/01/1990", "dob")
    print(f"DOB Confidence: {dob_conf}")

def test_authenticity():
    from app.enhanced_extractors import basic_authenticity_check
    print("\nTesting Authenticity Checks...")
    
    extracted = {
        "extracted_fields": {
            "pan_number": "ABCDE1234F", # 'E' at 4th pos is unusual
            "name": "John",
            "date_of_birth": "01/01/1990",
            "age": 34
        }
    }
    auth = basic_authenticity_check(extracted, "PAN")
    print(f"Authenticity Flags: {auth['flags']}")
    
    extracted_non_p = {
        "extracted_fields": {
            "pan_number": "ABCCX1234F", # 10 chars, 'C' is 4th char (Company)
            "name": "Acme Corp",
            "date_of_birth": "01/01/1990",
            "age": 34
        }
    }
    auth_non_p = basic_authenticity_check(extracted_non_p, "PAN")
    print(f"Authenticity Flags (Company): {auth_non_p['flags']}")
    print(f"Auto Terminate: {auth_non_p['auto_terminate']}")

if __name__ == "__main__":
    try:
        test_image_quality()
        test_field_confidence()
        test_authenticity()
        print("\nAll tests passed successfully!")
    except Exception as e:
        print(f"\nTests failed: {e}")
        import traceback
        traceback.print_exc()
