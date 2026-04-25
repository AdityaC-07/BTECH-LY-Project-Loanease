import io
import logging
import re
from typing import List, Dict, Optional, Tuple
from PIL import Image, ImageEnhance, ImageFilter
import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR
from rapidfuzz import fuzz
from datetime import datetime, timezone

from core.config import settings

logger = logging.getLogger("loanease.ocr")

# Memory guardrails for OCR preprocessing
MAX_IMAGE_SIDE = 2200
MAX_IMAGE_PIXELS = 4_500_000
MIN_WIDTH = 1200


def _is_bad_allocation_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "bad allocation" in message or "onnxruntimeerror" in message


def _downscale_for_onnx(candidate: np.ndarray, max_side: int = 1280) -> np.ndarray:
    height, width = candidate.shape[:2]
    longest_side = max(height, width)
    if longest_side <= max_side:
        return candidate

    scale = max_side / float(longest_side)
    new_width = max(320, int(width * scale))
    new_height = max(320, int(height * scale))
    return cv2.resize(candidate, (new_width, new_height), interpolation=cv2.INTER_AREA)

# Global OCR engine
_ocr_engine: Optional[RapidOCR] = None

def init_ocr():
    """Initialize RapidOCR engine"""
    global _ocr_engine
    try:
        _ocr_engine = RapidOCR()
        logger.info("RapidOCR engine initialized")
    except Exception as e:
        logger.error(f"Failed to initialize OCR: {e}")
        _ocr_engine = None

def ocr_ready() -> bool:
    """Check if OCR engine is ready"""
    return _ocr_engine is not None

def preprocess_image(file_bytes: bytes, extension: str) -> List[np.ndarray]:
    """Enhanced image preprocessing for OCR"""
    
    # Load image
    img = Image.open(io.BytesIO(file_bytes))
    if img.mode != 'RGB':
        img = img.convert('RGB')

    # Downscale very large inputs to prevent ONNX bad allocation
    width, height = img.size
    pixel_count = width * height

    if width > MAX_IMAGE_SIDE or height > MAX_IMAGE_SIDE or pixel_count > MAX_IMAGE_PIXELS:
        side_scale = min(MAX_IMAGE_SIDE / max(width, height), 1.0)
        pixel_scale = min((MAX_IMAGE_PIXELS / float(pixel_count)) ** 0.5, 1.0)
        scale = min(side_scale, pixel_scale)
        target_w = max(600, int(width * scale))
        target_h = max(600, int(height * scale))
        img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    
    # Enhance image
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.5)
    
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(1.2)
    
    # Denoise
    img = img.filter(ImageFilter.MedianFilter(size=3))
    
    # Upscale for better OCR
    if img.width < MIN_WIDTH:
        scale = MIN_WIDTH / img.width
        new_height = int(img.height * scale)
        img = img.resize((MIN_WIDTH, new_height), Image.Resampling.LANCZOS)
    
    # Convert to numpy array
    img_array = np.array(img)
    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    
    # Multiple preprocessing methods
    candidates = []
    
    # Method 1: Adaptive Gaussian
    thresh1 = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    candidates.append(cv2.cvtColor(thresh1, cv2.COLOR_GRAY2RGB))
    
    # Method 2: Adaptive Mean
    thresh2 = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 11, 2)
    candidates.append(cv2.cvtColor(thresh2, cv2.COLOR_GRAY2RGB))
    
    # Method 3: Otsu's thresholding
    _, thresh3 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    candidates.append(cv2.cvtColor(thresh3, cv2.COLOR_GRAY2RGB))
    
    # Add original
    candidates.append(img_array)
    
    return candidates

def run_ocr(preprocessed_img: List[np.ndarray]) -> Tuple[str, float]:
    """Run OCR on preprocessed images"""
    global _ocr_engine
    
    if not _ocr_engine:
        raise RuntimeError("OCR engine not initialized")
    
    best_text = ""
    best_conf = 0.0
    
    for idx, candidate in enumerate(preprocessed_img):
        try:
            # Secondary safety check before ONNX inference
            if candidate.shape[0] * candidate.shape[1] > MAX_IMAGE_PIXELS:
                scale = (MAX_IMAGE_PIXELS / float(candidate.shape[0] * candidate.shape[1])) ** 0.5
                new_w = max(600, int(candidate.shape[1] * scale))
                new_h = max(600, int(candidate.shape[0] * scale))
                candidate = cv2.resize(candidate, (new_w, new_h), interpolation=cv2.INTER_AREA)

            candidate = np.ascontiguousarray(candidate.astype(np.uint8, copy=False))

            result, _ = _ocr_engine(candidate)
            if result:
                text_lines = [item[1] for item in result]
                text = "\n".join(text_lines).strip()
                
                # Calculate confidence
                conf_values = []
                for item in result:
                    if len(item) >= 3:
                        try:
                            conf_values.append(float(item[2]))
                        except (ValueError, TypeError):
                            pass
                
                avg_conf = sum(conf_values) / len(conf_values) if conf_values else 0.0
                
                if avg_conf > best_conf:
                    best_text = text
                    best_conf = avg_conf
                    
        except Exception as e:
            if _is_bad_allocation_error(e):
                try:
                    emergency_candidate = _downscale_for_onnx(candidate, max_side=960)
                    emergency_candidate = np.ascontiguousarray(emergency_candidate.astype(np.uint8, copy=False))
                    result, _ = _ocr_engine(emergency_candidate)
                    if result:
                        text_lines = [item[1] for item in result]
                        text = "\n".join(text_lines).strip()

                        conf_values = []
                        for item in result:
                            if len(item) >= 3:
                                try:
                                    conf_values.append(float(item[2]))
                                except (ValueError, TypeError):
                                    pass

                        avg_conf = sum(conf_values) / len(conf_values) if conf_values else 0.0
                        if avg_conf > best_conf:
                            best_text = text
                            best_conf = avg_conf
                        logger.info("OCR recovered after emergency downscale (candidate=%s, conf=%.2f)", idx, avg_conf)
                        continue
                except Exception as emergency_exc:
                    logger.warning(
                        "OCR memory error on candidate %s; emergency retry failed (%s)",
                        idx,
                        str(emergency_exc).splitlines()[0],
                    )
                    continue

            logger.warning("OCR attempt failed (candidate=%s): %s", idx, str(e).splitlines()[0])
            continue
    
    return best_text, round(max(0.0, min(1.0, best_conf)), 2)

# Enhanced extractors
def extract_pan(ocr_text: str) -> Dict:
    """Extract PAN card information"""
    lines = [line.strip() for line in ocr_text.splitlines() if line.strip()]
    
    # PAN pattern
    pan_pattern = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
    pan_match = pan_pattern.search(ocr_text.upper())
    pan_number = pan_match.group(0) if pan_match else None
    
    # Name extraction
    name = None
    name_keywords = ["NAME", "INCOME TAX", "DEPARTMENT"]
    for i, line in enumerate(lines):
        if any(keyword in line.upper() for keyword in name_keywords):
            if i + 1 < len(lines):
                potential_name = lines[i + 1].strip()
                if len(potential_name) > 2 and potential_name.replace(" ", "").isalpha():
                    name = potential_name.title()
                    break
    
    # DOB extraction
    dob_patterns = [
        r"\b(\d{2}/\d{2}/\d{4})\b",
        r"\b(\d{2}-\d{2}-\d{4})\b"
    ]
    
    dob = None
    for pattern in dob_patterns:
        match = re.search(pattern, ocr_text)
        if match:
            dob = match.group(1)
            break
    
    # Calculate age
    age = None
    if dob:
        try:
            dob_dt = datetime.strptime(dob, "%d/%m/%Y")
            now = datetime.now(timezone.utc)
            age = now.year - dob_dt.year - ((now.month, now.day) < (dob_dt.month, dob_dt.day))
        except ValueError:
            pass
    
    return {
        "pan_number": pan_number,
        "name": name,
        "date_of_birth": dob,
        "age": age,
        "age_eligible": age is not None and 21 <= age <= 65
    }

def extract_aadhaar(ocr_text: str) -> Dict:
    """Extract Aadhaar card information"""
    lines = [line.strip() for line in ocr_text.splitlines() if line.strip()]
    
    # Aadhaar pattern
    aadhaar_pattern = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")
    aadhaar_matches = aadhaar_pattern.findall(ocr_text)
    
    aadhaar_number = None
    aadhaar_last4 = None
    if aadhaar_matches:
        # Clean and take the first match
        aadhaar_clean = re.sub(r"[\s-]", "", aadhaar_matches[0])
        if len(aadhaar_clean) == 12:
            aadhaar_number = aadhaar_clean
            aadhaar_last4 = aadhaar_clean[-4:]
    
    # Name extraction
    name = None
    for line in lines:
        if len(line) > 2 and line.replace(" ", "").isalpha():
            # Skip common non-name lines
            upper_line = line.upper()
            if not any(keyword in upper_line for keyword in ["GOVERNMENT", "INDIA", "UIDAI", "AADHAAR", "MALE", "FEMALE"]):
                name = line.title()
                break
    
    # DOB extraction
    dob_patterns = [
        r"\b(\d{2}/\d{2}/\d{4})\b",
        r"\b(\d{2}-\d{2}-\d{4})\b"
    ]
    
    dob = None
    for pattern in dob_patterns:
        match = re.search(pattern, ocr_text)
        if match:
            dob = match.group(1)
            break
    
    # Calculate age
    age = None
    if dob:
        try:
            dob_dt = datetime.strptime(dob, "%d/%m/%Y")
            now = datetime.now(timezone.utc)
            age = now.year - dob_dt.year - ((now.month, now.day) < (dob_dt.month, dob_dt.day))
        except ValueError:
            pass
    
    # Gender extraction
    gender = "Unknown"
    if "MALE" in ocr_text.upper():
        gender = "Male"
    elif "FEMALE" in ocr_text.upper():
        gender = "Female"
    
    return {
        "aadhaar_number": aadhaar_number,
        "aadhaar_last4": aadhaar_last4,
        "name": name,
        "date_of_birth": dob,
        "age": age,
        "gender": gender,
        "age_eligible": age is not None and 21 <= age <= 65
    }

def cross_validate_kyc(pan_data: Dict, aadhaar_data: Dict) -> Dict:
    """Cross-validate PAN and Aadhaar data"""
    pan_name = pan_data.get("name", "").strip().upper()
    aadhaar_name = aadhaar_data.get("name", "").strip().upper()
    
    # Name matching
    name_score = 0
    name_status = "MISMATCH"
    
    if pan_name and aadhaar_name:
        # Multiple fuzzy matching methods
        scores = [
            fuzz.token_sort_ratio(pan_name, aadhaar_name),
            fuzz.token_set_ratio(pan_name, aadhaar_name),
            fuzz.partial_ratio(pan_name, aadhaar_name),
            fuzz.ratio(pan_name, aadhaar_name)
        ]
        
        name_score = int(round(sum(scores) / len(scores)))
        
        if name_score >= 80:
            name_status = "MATCH"
        elif name_score >= 60:
            name_status = "PARTIAL"
    
    # DOB matching
    dob_match = False
    pan_dob = pan_data.get("date_of_birth")
    aadhaar_dob = aadhaar_data.get("date_of_birth")
    
    if pan_dob and aadhaar_dob:
        dob_match = pan_dob == aadhaar_dob
    
    # Overall KYC status
    if name_score >= 80 and dob_match:
        kyc_status = "VERIFIED"
    elif name_score >= 60:
        kyc_status = "PARTIAL"
    else:
        kyc_status = "FAILED"
    
    age_eligible = (
        pan_data.get("age_eligible", False) and 
        aadhaar_data.get("age_eligible", False)
    )
    
    return {
        "kyc_status": kyc_status,
        "name_match_score": name_score,
        "name_match_status": name_status,
        "dob_match": dob_match,
        "age_eligible": age_eligible,
        "overall_kyc_passed": kyc_status in ["VERIFIED", "PARTIAL"] and age_eligible
    }
