from __future__ import annotations

import importlib
import io
import logging
from typing import List, Union, Optional

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

# Try to import PDF libraries
try:
    import pypdfium2 as pdfium
    PDFIUM_AVAILABLE = True
except Exception:
    pdfium = None
    PDFIUM_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except Exception:
    PYMUPDF_AVAILABLE = False

try:
    import pdf2image
    PDF2IMAGE_AVAILABLE = True
except Exception:
    PDF2IMAGE_AVAILABLE = False

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
_rapidocr_engine = None

logger = logging.getLogger(__name__)


class UnsupportedDocumentError(ValueError):
    pass


def _load_optional_module(module_name: str):
    try:
        return importlib.import_module(module_name)
    except Exception:
        return None


def load_pdf_with_multiple_methods(file_bytes: bytes) -> Image.Image:
    """Load PDF using multiple available libraries with fallbacks"""
    
    # Method 1: PyMuPDF (best quality)
    if PYMUPDF_AVAILABLE:
        try:
            return _load_pdf_with_pymupdf(file_bytes)
        except Exception as e:
            logger.warning(f"PyMuPDF failed: {e}")
    
    # Method 2: pypdfium2
    if PDFIUM_AVAILABLE:
        try:
            return _load_pdf_with_pdfium(file_bytes)
        except Exception as e:
            logger.warning(f"pypdfium2 failed: {e}")
    
    # Method 3: pdf2image
    if PDF2IMAGE_AVAILABLE:
        try:
            return _load_pdf_with_pdf2image(file_bytes)
        except Exception as e:
            logger.warning(f"pdf2image failed: {e}")
    
    raise UnsupportedDocumentError(
        "Unable to process PDF. Please install one of: PyMuPDF, pypdfium2, or pdf2image"
    )


def _load_pdf_with_pymupdf(file_bytes: bytes) -> Image.Image:
    """Load PDF using PyMuPDF (highest quality)"""
    import fitz
    
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    if len(doc) == 0:
        raise UnsupportedDocumentError("PDF has no pages")
    
    page = doc[0]
    # High DPI for better OCR
    mat = fitz.Matrix(3.0, 3.0)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    
    # Convert to PIL Image
    img_data = pix.tobytes("ppm")
    pil_img = Image.open(io.BytesIO(img_data))
    
    doc.close()
    return pil_img.convert("RGB")


def _load_pdf_with_pdfium(file_bytes: bytes) -> Image.Image:
    """Load PDF using pypdfium2"""
    if pdfium is None:
        raise UnsupportedDocumentError("pypdfium2 not available")
    
    pdf = pdfium.PdfDocument(file_bytes)
    if len(pdf) == 0:
        raise UnsupportedDocumentError("Unable to read first page from PDF")
    
    page = pdf[0]
    # High render scale for better OCR
    bitmap = page.render(scale=4.0)
    pil_img = bitmap.to_pil().convert("RGB")
    page.close()
    pdf.close()
    return pil_img


def _load_pdf_with_pdf2image(file_bytes: bytes) -> Image.Image:
    """Load PDF using pdf2image"""
    import pdf2image
    
    # Convert PDF to images
    images = pdf2image.convert_from_bytes(file_bytes, dpi=300)
    if not images:
        raise UnsupportedDocumentError("Unable to convert PDF to images")
    
    return images[0].convert("RGB")


def load_image_from_bytes(file_bytes: bytes, extension: str) -> Image.Image:
    """Load image from bytes with enhanced PDF support"""
    ext = extension.lower().strip(".")
    
    if ext in {"jpg", "jpeg", "png", "bmp", "tiff", "webp"}:
        return Image.open(io.BytesIO(file_bytes)).convert("RGB")
    
    if ext == "pdf":
        return load_pdf_with_multiple_methods(file_bytes)
    
    raise UnsupportedDocumentError(f"Unsupported format: {ext}. Supported: JPG, PNG, PDF, BMP, TIFF, WebP")


def enhance_image_for_ocr(img: Image.Image) -> Image.Image:
    """Enhance image quality for better OCR"""
    # Convert to RGB if needed
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    # Enhance contrast
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.5)
    
    # Enhance sharpness
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(1.2)
    
    # Denoise
    img = img.filter(ImageFilter.MedianFilter(size=3))
    
    return img


def upscale_for_ocr(img: Image.Image) -> Image.Image:
    """Upscale image for better OCR with improved quality"""
    min_width = 1200  # Increased from 800 for better OCR
    if img.width >= min_width:
        return img
    
    # Calculate scale factor
    scale = min_width / float(img.width)
    new_height = int(img.height * scale)
    
    # Use high-quality resampling
    return img.resize((min_width, new_height), Image.Resampling.LANCZOS)


def advanced_deskew(img: np.ndarray) -> np.ndarray:
    """Advanced deskewing with multiple angle detection methods"""
    
    # Method 1: Hough Lines (existing)
    lines = cv2.HoughLines(img, 1, np.pi / 180, 160)
    angles = []
    
    if lines is not None and len(lines) > 0:
        for line in lines[:80]:  # Limit to first 80 lines
            rho, theta = line[0]
            angle = (theta * 180 / np.pi) - 90
            if -20 <= angle <= 20:
                angles.append(angle)
    
    # Method 2: PCA-based angle detection
    if len(angles) == 0:
        angles.append(_detect_angle_with_pca(img))
    
    # Method 3: Projection-based angle detection
    if len(angles) == 0:
        angles.append(_detect_angle_with_projection(img))
    
    if not angles:
        return img
    
    # Use median angle for stability
    median_angle = float(np.median(angles))
    
    # Apply rotation
    h, w = img.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, median_angle, 1.0)
    rotated = cv2.warpAffine(
        img, matrix, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    
    return rotated


def _detect_angle_with_pca(img: np.ndarray) -> float:
    """Detect skew angle using PCA"""
    # Find contours
    contours, _ = cv2.findContours(img, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        return 0.0
    
    # Combine all points
    all_points = np.vstack([contour.reshape(-1, 2) for contour in contours])
    
    # PCA
    mean, eigenvectors = cv2.PCACompute(all_points, mean=None)
    
    # Calculate angle from principal component
    angle = np.arctan2(eigenvectors[0, 1], eigenvectors[0, 0]) * 180 / np.pi
    
    return angle if -20 <= angle <= 20 else 0.0


def _detect_angle_with_projection(img: np.ndarray) -> float:
    """Detect skew angle using projection profile"""
    h, w = img.shape
    angles = np.arange(-15, 16, 0.5)
    
    max_variance = 0
    best_angle = 0
    
    for angle in angles:
        # Rotate image
        center = (w // 2, h // 2)
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(img, matrix, (w, h), flags=cv2.INTER_CUBIC)
        
        # Calculate horizontal projection
        h_proj = np.sum(rotated, axis=1)
        
        # Calculate variance (higher variance = better alignment)
        variance = np.var(h_proj)
        
        if variance > max_variance:
            max_variance = variance
            best_angle = angle
    
    return best_angle


def enhanced_preprocess_image(file_bytes: bytes, extension: str) -> List[np.ndarray]:
    """Enhanced image preprocessing for better OCR"""
    
    # Load and enhance image
    pil_img = load_image_from_bytes(file_bytes, extension)
    pil_img = enhance_image_for_ocr(pil_img)
    pil_img = upscale_for_ocr(pil_img)
    
    # Convert to numpy array
    img = np.array(pil_img)
    
    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    
    # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    contrast = clahe.apply(gray)
    
    # Denoise
    denoised = cv2.bilateralFilter(contrast, 9, 75, 75)
    
    # Multiple thresholding methods
    thresh_methods = []
    
    # Method 1: Adaptive Gaussian
    thresh1 = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    thresh_methods.append(thresh1)
    
    # Method 2: Adaptive Mean
    thresh2 = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 11, 2
    )
    thresh_methods.append(thresh2)
    
    # Method 3: Otsu's thresholding
    _, thresh3 = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    thresh_methods.append(thresh3)
    
    # Apply deskewing to each method
    deskewed_methods = []
    for thresh in thresh_methods:
        deskewed = advanced_deskew(thresh)
        deskewed_methods.append(deskewed)
    
    # Create RGB versions for OCR
    gray_rgb = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
    contrast_rgb = cv2.cvtColor(contrast, cv2.COLOR_GRAY2RGB)
    denoised_rgb = cv2.cvtColor(denoised, cv2.COLOR_GRAY2RGB)
    
    # Add deskewed versions
    for deskewed in deskewed_methods:
        deskewed_rgb = cv2.cvtColor(deskewed, cv2.COLOR_GRAY2RGB)
        gray_rgb = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
        contrast_rgb = cv2.cvtColor(contrast, cv2.COLOR_GRAY2RGB)
        denoised_rgb = cv2.cvtColor(denoised, cv2.COLOR_GRAY2RGB)
    
    # Return all preprocessing candidates
    candidates = [
        img,           # Original
        gray_rgb,      # Grayscale
        contrast_rgb,  # Enhanced contrast
        denoised_rgb,  # Denoised
    ]
    
    # Add deskewed versions
    for deskewed in deskewed_methods:
        deskewed_rgb = cv2.cvtColor(deskewed, cv2.COLOR_GRAY2RGB)
        candidates.append(deskewed_rgb)
    
    return candidates


def run_enhanced_ocr(preprocessed_img: Union[np.ndarray, List[np.ndarray]]) -> Tuple[str, float]:
    """Enhanced OCR with better confidence scoring"""
    global _rapidocr_engine
    
    rapidocr_module = _load_optional_module("rapidocr_onnxruntime")
    if rapidocr_module is None:
        raise RuntimeError("RapidOCR is not available. Install rapidocr-onnxruntime.")
    
    if _rapidocr_engine is None:
        _rapidocr_engine = rapidocr_module.RapidOCR()
    
    candidates = preprocessed_img if isinstance(preprocessed_img, list) else [preprocessed_img]
    
    best_text = ""
    best_conf = 0.0
    best_score = -1.0
    best_method = ""
    
    for i, candidate in enumerate(candidates):
        try:
            rapid_result, _ = _rapidocr_engine(candidate)
            if not rapid_result:
                continue
            
            # Extract text and confidence
            text_lines = []
            conf_vals = []
            
            for item in rapid_result:
                if len(item) >= 2:
                    text_lines.append(str(item[1]))
                if len(item) >= 3:
                    try:
                        conf_vals.append(float(item[2]))
                    except (ValueError, TypeError):
                        pass
            
            text = "\n".join(text_lines).strip()
            if not text:
                continue
            
            # Calculate average confidence
            avg_conf = sum(conf_vals) / len(conf_vals) if conf_vals else 0.0
            
            # Enhanced scoring: confidence + text quality factors
            text_quality_score = calculate_text_quality(text)
            score = (avg_conf * 0.7) + (text_quality_score * 0.3)
            
            # Method bonus
            method_bonus = get_method_bonus(i, len(candidates))
            score += method_bonus
            
            if score > best_score:
                best_score = score
                best_text = text
                best_conf = avg_conf
                best_method = f"method_{i}"
                
        except Exception as e:
            logger.warning(f"OCR failed for candidate {i}: {e}")
            continue
    
    if best_text:
        logger.info(f"Best OCR result from {best_method} with score {best_score:.2f}")
        return best_text, round(max(0.0, min(1.0, best_conf)), 2)
    
    raise RuntimeError("OCR failed to extract any text from all candidates")


def calculate_text_quality(text: str) -> float:
    """Calculate text quality score"""
    if not text:
        return 0.0
    
    score = 0.0
    
    # Length score (prefer reasonable amount of text)
    length = len(text)
    if 50 <= length <= 1000:
        score += 0.3
    elif 20 <= length <= 2000:
        score += 0.2
    else:
        score += 0.1
    
    # Line count score
    lines = text.split('\n')
    if 5 <= len(lines) <= 50:
        score += 0.2
    elif 2 <= len(lines) <= 100:
        score += 0.1
    
    # Word diversity score
    words = text.split()
    unique_words = set(words.lower() for word in words if len(word) > 2)
    if len(words) > 0:
        diversity = len(unique_words) / len(words)
        score += diversity * 0.2
    
    # Pattern detection score (look for expected patterns)
    has_pan = bool(re.search(r'\b[A-Z]{5}[0-9]{4}[A-Z]\b', text))
    has_aadhaar = bool(re.search(r'\b\d{4}\s?\d{4}\s?\d{4}\b', text))
    has_date = bool(re.search(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b', text))
    
    if has_pan or has_aadhaar:
        score += 0.2
    if has_date:
        score += 0.1
    
    return min(score, 1.0)


def get_method_bonus(index: int, total_methods: int) -> float:
    """Get bonus score based on preprocessing method"""
    # Prioritize certain methods
    if index == 0:  # Original image
        return 0.05
    elif index == 2:  # Enhanced contrast
        return 0.1
    elif index >= 4:  # Deskewed versions
        return 0.15
    else:
        return 0.0


def get_ocr_engine_info() -> Tuple[str, List[str]]:
    """Get OCR engine information"""
    rapidocr_module = _load_optional_module("rapidocr_onnxruntime")
    if rapidocr_module is None:
        return "unavailable", []
    
    version = getattr(rapidocr_module, "__version__", "installed")
    
    # Check PDF processing capabilities
    pdf_methods = []
    if PYMUPDF_AVAILABLE:
        pdf_methods.append("PyMuPDF")
    if PDFIUM_AVAILABLE:
        pdf_methods.append("pypdfium2")
    if PDF2IMAGE_AVAILABLE:
        pdf_methods.append("pdf2image")
    
    return str(version), ["en", "hi"] + pdf_methods


# Import regex for text quality calculation
import re
