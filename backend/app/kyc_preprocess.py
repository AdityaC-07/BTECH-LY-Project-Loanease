from __future__ import annotations

import io
import cv2
import numpy as np
from PIL import Image

try:
    import pypdfium2 as pdfium
except Exception:
    pdfium = None

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
_rapidocr_engine = None


class UnsupportedDocumentError(ValueError):
    pass


def _load_pdf_with_pdfium(file_bytes: bytes) -> Image.Image:
    if pdfium is None:
        raise UnsupportedDocumentError("PDF upload requires pypdfium2")
    
    pdf = pdfium.PdfDocument(file_bytes)
    if len(pdf) == 0:
        raise UnsupportedDocumentError("Unable to read first page from PDF")
    
    page = pdf[0]
    bitmap = page.render(scale=4.0)
    pil_img = bitmap.to_pil().convert("RGB")
    page.close()
    pdf.close()
    return pil_img


def _load_image_from_bytes(file_bytes: bytes, extension: str) -> Image.Image:
    ext = extension.lower().strip(".")
    if ext in {"jpg", "jpeg", "png"}:
        return Image.open(io.BytesIO(file_bytes)).convert("RGB")
    if ext == "pdf":
        return _load_pdf_with_pdfium(file_bytes)
    raise UnsupportedDocumentError("Only JPG, PNG and PDF are supported")


def _upscale_for_ocr(img: Image.Image) -> Image.Image:
    min_width = 800
    if img.width >= min_width:
        return img
    scale = min_width / float(img.width)
    new_height = int(img.height * scale)
    return img.resize((min_width, new_height), Image.Resampling.LANCZOS)


def preprocess_image(file_bytes: bytes, extension: str) -> list[np.ndarray]:
    pil_img = _load_image_from_bytes(file_bytes, extension)
    pil_img = _upscale_for_ocr(pil_img)
    img = np.array(pil_img)
    
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    contrast = clahe.apply(gray)
    blurred = cv2.GaussianBlur(contrast, (3, 3), 0)
    thresh = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    
    gray_rgb = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
    contrast_rgb = cv2.cvtColor(contrast, cv2.COLOR_GRAY2RGB)
    thresh_rgb = cv2.cvtColor(thresh, cv2.COLOR_GRAY2RGB)
    
    return [img, gray_rgb, contrast_rgb, thresh_rgb]


def run_ocr(preprocessed_img: np.ndarray | list[np.ndarray]) -> tuple[str, float]:
    global _rapidocr_engine
    
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        raise RuntimeError("RapidOCR not available. Install rapidocr-onnxruntime.")
    
    if _rapidocr_engine is None:
        _rapidocr_engine = RapidOCR()
    
    candidates = preprocessed_img if isinstance(preprocessed_img, list) else [preprocessed_img]
    best_text = ""
    best_conf = 0.0
    best_score = -1.0
    
    for candidate in candidates:
        try:
            rapid_result, _ = _rapidocr_engine(candidate)
        except Exception:
            continue
        
        if not rapid_result:
            continue
        
        text_lines = []
        conf_vals = []
        for item in rapid_result:
            if len(item) >= 2:
                text_lines.append(str(item[1]))
            if len(item) >= 3:
                try:
                    conf_vals.append(float(item[2]))
                except Exception:
                    pass
        
        text = "\n".join(text_lines).strip()
        avg_conf = sum(conf_vals) / len(conf_vals) if conf_vals else 0.0
        score = avg_conf + min(len(text) / 250.0, 0.25)
        
        if score > best_score:
            best_score = score
            best_text = text
            best_conf = avg_conf
    
    if best_text:
        return best_text, round(max(0.0, min(1.0, best_conf)), 2)
    
    return "", 0.0
