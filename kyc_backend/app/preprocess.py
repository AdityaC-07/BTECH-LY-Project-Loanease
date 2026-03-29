from __future__ import annotations

import importlib
import io

import cv2
import numpy as np
from PIL import Image
import pytesseract

try:
    import pypdfium2 as pdfium
except Exception:  # optional dependency fallback
    pdfium = None

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
_rapidocr_engine = None


def _load_optional_module(module_name: str):
    try:
        return importlib.import_module(module_name)
    except Exception:
        return None


class UnsupportedDocumentError(ValueError):
    pass


def _load_pdf_with_pdfium(file_bytes: bytes) -> Image.Image:
    if pdfium is None:
        raise UnsupportedDocumentError(
            "PDF upload requires pypdfium2. Install pypdfium2 to process PDF documents."
        )

    pdf = pdfium.PdfDocument(file_bytes)
    if len(pdf) == 0:
        raise UnsupportedDocumentError("Unable to read first page from PDF")

    page = pdf[0]
    bitmap = page.render(scale=3.0)
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


def _deskew(binary_img: np.ndarray) -> np.ndarray:
    lines = cv2.HoughLines(binary_img, 1, np.pi / 180, 160)
    if lines is None or len(lines) == 0:
        return binary_img

    angles: list[float] = []
    for line in lines[:80]:
        rho, theta = line[0]
        angle = (theta * 180 / np.pi) - 90
        if -20 <= angle <= 20:
            angles.append(angle)

    if not angles:
        return binary_img

    median_angle = float(np.median(angles))
    h, w = binary_img.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, median_angle, 1.0)
    rotated = cv2.warpAffine(
        binary_img,
        matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return rotated


def preprocess_image(file_bytes: bytes, extension: str) -> np.ndarray:
    pil_img = _load_image_from_bytes(file_bytes, extension)
    pil_img = _upscale_for_ocr(pil_img)

    img = np.array(pil_img)
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    contrast = clahe.apply(gray)

    blurred = cv2.GaussianBlur(contrast, (3, 3), 0)

    thresh = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11,
        2,
    )

    return _deskew(thresh)


def run_ocr(preprocessed_img: np.ndarray) -> tuple[str, float]:
    config = "--oem 3 --psm 6"

    # Primary OCR path: Tesseract
    try:
        text = pytesseract.image_to_string(preprocessed_img, lang="eng+hin", config=config)

        data = pytesseract.image_to_data(
            preprocessed_img,
            lang="eng+hin",
            config=config,
            output_type=pytesseract.Output.DICT,
        )

        confidences = []
        for conf in data.get("conf", []):
            try:
                val = float(conf)
                if val >= 0:
                    confidences.append(val)
            except Exception:
                continue

        avg_conf = (sum(confidences) / len(confidences)) / 100 if confidences else 0.0
        return text, round(max(0.0, min(1.0, avg_conf)), 2)
    except Exception:
        pass

    # Fallback OCR path 1: RapidOCR (Python-only)
    global _rapidocr_engine
    rapidocr_module = _load_optional_module("rapidocr_onnxruntime")
    if rapidocr_module is not None:
        if _rapidocr_engine is None:
            _rapidocr_engine = rapidocr_module.RapidOCR()

        rapid_result, _ = _rapidocr_engine(preprocessed_img)
        if rapid_result:
            text_lines = []
            conf_vals = []
            for item in rapid_result:
                # Format: [box, text, score]
                if len(item) >= 2:
                    text_lines.append(str(item[1]))
                if len(item) >= 3:
                    try:
                        conf_vals.append(float(item[2]))
                    except Exception:
                        pass

            text = "\n".join(text_lines)
            avg_conf = sum(conf_vals) / len(conf_vals) if conf_vals else 0.0
            return text, round(max(0.0, min(1.0, avg_conf)), 2)

    raise RuntimeError(
        "No OCR engine available. Install Tesseract (eng+hin) or install rapidocr-onnxruntime."
    )


def get_tesseract_info() -> tuple[str, list[str]]:
    try:
        version = str(pytesseract.get_tesseract_version())
    except Exception:
        version = "unavailable"

    try:
        langs = sorted(pytesseract.get_languages(config=""))
    except Exception:
        langs = []

    return version, langs
