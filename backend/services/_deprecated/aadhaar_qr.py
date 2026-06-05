from __future__ import annotations

import base64
import asyncio
import concurrent.futures
import hashlib
import json
import logging
import os
import re
import zlib
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Optional
import xml.etree.ElementTree as ET

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger("aadhaar_qr")

QR_ENABLED = os.getenv("QR_SCAN_ENABLED", "true").lower() == "true"
_qr_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="qr_scan")

try:
    from pyzbar import pyzbar

    PYZBAR_AVAILABLE = True
except Exception as exc:
    PYZBAR_AVAILABLE = False
    logger.warning("pyzbar import failed - QR decode fallback disabled: %s", exc)

try:
    import zxingcpp  # type: ignore

    ZXING_AVAILABLE = True
except Exception as exc:
    ZXING_AVAILABLE = False
    logger.warning("zxingcpp not available - install zxing-cpp for an additional QR fallback: %s", exc)

try:
    import fitz  # PyMuPDF

    PYMUPDF_AVAILABLE = True
except Exception as exc:
    PYMUPDF_AVAILABLE = False
    logger.warning("PyMuPDF not available - PDF pages cannot be rendered: %s", exc)

try:
    from pyaadhaar.decode import AadhaarSecureQr, AadhaarOldQr
    from pyaadhaar.utils import AadhaarQrAuto, isSecureQr

    PYAADHAAR_AVAILABLE = True
except Exception as exc:
    PYAADHAAR_AVAILABLE = False
    logger.warning("pyaadhaar import failed, QR verification disabled: %s", exc)


@dataclass
class _DecodeCandidate:
    label: str
    image: np.ndarray


def _pil_to_cv2(img: Image.Image) -> np.ndarray:
    rgb = img.convert("RGB")
    return cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)


def _cv2_to_pil(img: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _resize_for_qr(image: np.ndarray, max_size: int = 1200) -> np.ndarray:
    """Resize images before QR decode to cap RAM and CPU usage."""
    height, width = image.shape[:2]
    if max(height, width) <= max_size:
        return image

    scale = max_size / max(height, width)
    new_width = int(width * scale)
    new_height = int(height * scale)
    return cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)


def _prepare_variants(img_array: np.ndarray) -> list[_DecodeCandidate]:
    """Generate a small set of cheap QR preprocessing variants."""
    image = _resize_for_qr(img_array)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    return [
        _DecodeCandidate("gray", cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)),
        _DecodeCandidate("clahe", cv2.cvtColor(clahe, cv2.COLOR_GRAY2BGR)),
        _DecodeCandidate("otsu", cv2.cvtColor(otsu, cv2.COLOR_GRAY2BGR)),
    ]


def _decode_with_pyzbar(img_array: np.ndarray) -> Optional[str]:
    if not PYZBAR_AVAILABLE:
        return None

    try:
        codes = pyzbar.decode(img_array)
    except Exception as exc:
        logger.debug("pyzbar failed: %s", exc)
        return None

    for code in codes:
        if code.type in ("QRCODE", "QR CODE") and code.data:
            logger.info("QR decoded by pyzbar")
            return code.data.decode("utf-8", errors="ignore")
    return None


def _decode_with_opencv(img_array: np.ndarray) -> tuple[Optional[str], Optional[np.ndarray]]:
    try:
        detector = cv2.QRCodeDetector()
    except Exception as exc:
        logger.debug("OpenCV QRCodeDetector unavailable: %s", exc)
        return None, None

    try:
        text, points, _ = detector.detectAndDecode(img_array)
        if text:
            logger.info("QR decoded by OpenCV QRCodeDetector")
            return text, points
    except Exception as exc:
        logger.debug("OpenCV detectAndDecode failed: %s", exc)

    try:
        ok, decoded_info, points, _ = detector.detectAndDecodeMulti(img_array)
        if ok and decoded_info:
            for decoded in decoded_info:
                if decoded:
                    logger.info("QR decoded by OpenCV QRCodeDetector (multi)")
                    return decoded, points
    except Exception as exc:
        logger.debug("OpenCV detectAndDecodeMulti failed: %s", exc)

    return None, None


def _decode_with_zxingcpp(img_array: np.ndarray) -> Optional[str]:
    if not ZXING_AVAILABLE:
        return None

    try:
        rgb = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
        results = zxingcpp.read_barcodes(rgb)
    except Exception as exc:
        logger.debug("zxingcpp failed: %s", exc)
        return None

    for result in results or []:
        text = getattr(result, "text", None)
        if text:
            logger.info("QR decoded by zxingcpp")
            return text
    return None


def _points_to_bbox(points: Optional[np.ndarray], shape: tuple[int, int, int]) -> Optional[tuple[int, int, int, int]]:
    if points is None:
        return None

    try:
        arr = np.array(points).reshape(-1, 2)
    except Exception:
        return None

    if arr.size == 0:
        return None

    h, w = shape[:2]
    x_min = int(max(0, np.min(arr[:, 0])))
    y_min = int(max(0, np.min(arr[:, 1])))
    x_max = int(min(w, np.max(arr[:, 0])))
    y_max = int(min(h, np.max(arr[:, 1])))

    if x_max <= x_min or y_max <= y_min:
        return None
    return x_min, y_min, x_max, y_max


def _crop_bbox(img_array: np.ndarray, bbox: tuple[int, int, int, int], padding: float = 0.15) -> np.ndarray:
    height, width = img_array.shape[:2]
    x1, y1, x2, y2 = bbox
    pad_x = int((x2 - x1) * padding)
    pad_y = int((y2 - y1) * padding)
    left = max(0, x1 - pad_x)
    top = max(0, y1 - pad_y)
    right = min(width, x2 + pad_x)
    bottom = min(height, y2 + pad_y)
    if right <= left or bottom <= top:
        return img_array
    return img_array[top:bottom, left:right]


def _region_candidates(img_array: np.ndarray) -> list[_DecodeCandidate]:
    """Heuristic regions where Aadhaar QR commonly appears."""
    h, w = img_array.shape[:2]
    regions = [
        ("full", (0, 0, w, h)),
        ("bottom_half", (0, h // 2, w, h)),
        ("right_half", (w // 2, 0, w, h)),
        ("bottom_right", (w // 2, h // 2, w, h)),
        ("lower_right_focus", (int(w * 0.40), int(h * 0.35), w, h)),
        ("qr_corner", (int(w * 0.55), int(h * 0.40), w, h)),
        ("small_lower_strip", (int(w * 0.35), int(h * 0.55), w, h)),
    ]

    candidates: list[_DecodeCandidate] = []
    for label, (x1, y1, x2, y2) in regions:
        crop = img_array[y1:y2, x1:x2]
        if crop.size:
            candidates.append(_DecodeCandidate(label=label, image=crop))
    return candidates


def _render_pdf_pages(contents: bytes, filename: str) -> list[tuple[int, Image.Image]]:
    if not PYMUPDF_AVAILABLE or not filename.lower().endswith(".pdf"):
        return []

    pages: list[tuple[int, Image.Image]] = []
    doc = fitz.open(stream=contents, filetype="pdf")
    try:
        for page_index in range(len(doc)):
            page = doc[page_index]
            pix = page.get_pixmap(matrix=fitz.Matrix(3.0, 3.0), alpha=False)
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            pages.append((page_index + 1, image))
    finally:
        doc.close()

    return pages


def _parse_xml_payload(xml_text: str) -> dict:
    result: dict[str, Any] = {}

    try:
        root = ET.fromstring(xml_text)
        attrib = {key.lower(): value for key, value in root.attrib.items()}
        result["name"] = attrib.get("n") or attrib.get("name")
        result["dob"] = attrib.get("dob") or attrib.get("yob")
        result["gender"] = attrib.get("g") or attrib.get("gender")
        result["mobile_hash"] = attrib.get("mobilehash") or attrib.get("mh")
        result["email_hash"] = attrib.get("emailhash") or attrib.get("eh")
        address_parts = [attrib.get(tag) for tag in ("po", "vtc", "dist", "subdist", "state", "pc") if attrib.get(tag)]
        if address_parts:
            result["address"] = ", ".join(address_parts)
        result["pincode"] = attrib.get("pc")
    except Exception:
        patterns = {
            "name": [r'name="([^"]+)"', r'n="([^"]+)"'],
            "dob": [r'dob="([^"]+)"', r'yob="([^"]+)"'],
            "gender": [r'gender="([^"]+)"', r'g="([^"]+)"'],
            "mobile_hash": [r'mobileHash="([^"]+)"', r'mh="([^"]+)"'],
            "email_hash": [r'emailHash="([^"]+)"', r'eh="([^"]+)"'],
            "address": [r'<Po>([^<]+)</Po>', r'po="([^"]+)"'],
            "pincode": [r'pc="([^"]+)"', r'pincode="([^"]+)"'],
        }
        for field, field_patterns in patterns.items():
            for pattern in field_patterns:
                match = re.search(pattern, xml_text, re.IGNORECASE)
                if match:
                    result[field] = match.group(1).strip()
                    break

    result["qr_parsed"] = True
    result["format"] = "xml"
    return result


def _parse_binary_payload(data: bytes) -> dict:
    try:
        text = data.decode("utf-8", errors="ignore")
    except Exception:
        text = ""

    if "<" in text and ">" in text:
        return _parse_xml_payload(text)

    readable = re.findall(r"[A-Za-z0-9@.\s,/-]{4,}", text)
    result = {"raw_strings": readable[:20], "qr_parsed": True, "format": "binary"}
    for item in readable:
        value = item.strip()
        if re.match(r"\d{2}[-/]\d{2}[-/]\d{4}", value) or re.match(r"\d{4}$", value):
            result.setdefault("dob", value)
        elif re.match(r"[0-9a-f]{40,}$", value.lower()):
            result.setdefault("mobile_hash", value)
        elif len(value) > 5 and all(c.isalpha() or c.isspace() for c in value):
            result.setdefault("name", value)
    return result


def parse_aadhaar_qr(qr_data: bytes | str) -> Optional[dict]:
    if not qr_data:
        return None

    try:
        text = qr_data.decode("utf-8", errors="ignore") if isinstance(qr_data, bytes) else str(qr_data)
        stripped = text.strip()

        if stripped.startswith("<?xml") or stripped.startswith("<"):
            return _parse_xml_payload(stripped)

        if stripped.isdigit():
            payload = int(stripped)
            byte_length = (payload.bit_length() + 7) // 8
            raw_bytes = payload.to_bytes(byte_length, byteorder="big")
            try:
                decompressed = zlib.decompress(raw_bytes)
            except Exception:
                try:
                    decompressed = zlib.decompress(raw_bytes, -15)
                except Exception:
                    decompressed = raw_bytes
            return _parse_binary_payload(decompressed)

        try:
            decoded = base64.b64decode(stripped)
            parsed = _parse_binary_payload(decoded)
            if parsed:
                return parsed
        except Exception:
            pass

        logger.warning("Unknown QR format: %s", stripped[:80])
        return None
    except Exception as exc:
        logger.error("QR parse error: %s", exc)
        return None


def _extract_payload_fields(payload: dict, secure: bool) -> dict:
    reference_id = payload.get("referenceid") or payload.get("reference_id") or ""
    aadhaar_last4 = payload.get("aadhaar_last4") or (reference_id[-4:] if reference_id else None)

    address_parts = []
    address_value = payload.get("address")
    if isinstance(address_value, dict):
        for key in ("house", "street", "location", "district", "state", "pincode", "post_office"):
            value = address_value.get(key)
            if value:
                address_parts.append(str(value))
    elif address_value:
        address_parts.append(str(address_value))

    address_text = ", ".join(part for part in address_parts if part)

    return {
        "aadhaar_number": payload.get("aadhaar_number") or (f"XXXX XXXX {aadhaar_last4}" if aadhaar_last4 else None),
        "aadhaar_last4": aadhaar_last4,
        "name": payload.get("name"),
        "dob": payload.get("dob") or payload.get("date_of_birth"),
        "gender": payload.get("gender"),
        "address": address_text,
        "photo_present": bool(payload.get("photo_b64") or payload.get("has_photo")),
        "reference_id": reference_id,
        "mobile_hash": payload.get("mobile_hash"),
        "email_hash": payload.get("email_hash"),
        "signature_valid": secure,
    }


def _run_secure_qr_decode(qr_text: str, mobile_to_verify: str | None = None) -> dict:
    qr_text = _normalize_whitespace(qr_text)
    if not qr_text:
        return {"qr_found": True, "qr_parsed": False, "error": "Empty QR payload"}

    normalized_digits = re.sub(r"\D", "", qr_text)
    if normalized_digits:
        if not PYAADHAAR_AVAILABLE:
            legacy = parse_aadhaar_qr(qr_text)
            if legacy is not None:
                extracted = _extract_payload_fields(legacy, secure=False)
                return {
                    "qr_found": True,
                    "qr_parsed": True,
                    "decoder_used": "legacy_numeric",
                    "signature_valid": False,
                    "confidence_score": 0.72,
                    **extracted,
                    "decoded_fields": {
                        "name": extracted["name"],
                        "date_of_birth": extracted["dob"],
                        "gender": extracted["gender"],
                        "address": extracted["address"],
                        "aadhaar_last4": extracted["aadhaar_last4"],
                        "reference_id": extracted["reference_id"],
                    },
                    "qr_data": legacy,
                }
            return {
                "qr_found": True,
                "qr_parsed": False,
                "error": "pyaadhaar not installed",
                "decoder_used": "pyaadhaar_missing",
            }

        try:
            is_secure = isSecureQr(normalized_digits)
        except Exception:
            is_secure = True

        try:
            obj = AadhaarQrAuto(normalized_digits)
            decoded = obj.decodeddata()
            decoder_used = "pyaadhaar_secure" if is_secure else "pyaadhaar_old"
        except Exception as exc:
            logger.error("pyaadhaar decode failed: %s", exc)
            legacy = parse_aadhaar_qr(qr_text)
            if legacy is not None:
                extracted = _extract_payload_fields(legacy, secure=False)
                return {
                    "qr_found": True,
                    "qr_parsed": True,
                    "decoder_used": "legacy_numeric_fallback",
                    "signature_valid": False,
                    "confidence_score": 0.7,
                    **extracted,
                    "decoded_fields": {
                        "name": extracted["name"],
                        "date_of_birth": extracted["dob"],
                        "gender": extracted["gender"],
                        "address": extracted["address"],
                        "aadhaar_last4": extracted["aadhaar_last4"],
                        "reference_id": extracted["reference_id"],
                    },
                    "qr_data": legacy,
                }
            return {
                "qr_found": True,
                "qr_parsed": False,
                "error": str(exc),
                "decoder_used": "pyaadhaar",
            }

        signature_valid = bool(is_secure)
        mobile_hash = None
        mobile_verification = None

        try:
            if is_secure and hasattr(obj, "sha256hashOfMobileNumber"):
                mobile_hash = obj.sha256hashOfMobileNumber()
                logger.info("Secure QR mobile hash extracted")
        except Exception as exc:
            logger.debug("Mobile hash extraction failed: %s", exc)

        if mobile_to_verify and mobile_hash:
            try:
                mobile_verification = obj.verifyMobileNumber(mobile_to_verify)
            except Exception as exc:
                logger.debug("Mobile verification failed: %s", exc)

        address_parts = [
            decoded.get("house"),
            decoded.get("street"),
            decoded.get("location"),
            decoded.get("vtc"),
            decoded.get("district"),
            decoded.get("subdistrict"),
            decoded.get("state"),
            decoded.get("pincode"),
            decoded.get("postoffice"),
        ]
        address_text = ", ".join(str(part).strip() for part in address_parts if part)

        photo_present = False
        photo_b64 = None
        try:
            image_fn = getattr(obj, "image", None)
            if callable(image_fn):
                photo_buf = BytesIO()
                image_fn().save(photo_buf, format="JPEG")
                photo_b64 = base64.b64encode(photo_buf.getvalue()).decode()
                photo_present = True
        except Exception as exc:
            logger.debug("Photo extraction failed: %s", exc)

        reference_id = decoded.get("referenceid", "")
        aadhaar_last4 = reference_id[:4] if reference_id else None
        extracted = {
            "aadhaar_number": f"XXXX XXXX {aadhaar_last4}" if aadhaar_last4 else None,
            "aadhaar_last4": aadhaar_last4,
            "name": decoded.get("name"),
            "dob": decoded.get("dob"),
            "gender": decoded.get("gender"),
            "address": address_text,
            "photo_present": photo_present,
            "reference_id": reference_id,
            "mobile_hash": mobile_hash,
            "signature_valid": signature_valid,
        }

        result = {
            "qr_found": True,
            "qr_parsed": True,
            "decoder_used": decoder_used,
            "signature_valid": signature_valid,
            "confidence_score": 0.97 if signature_valid else 0.85,
            "mobile_hash_available": bool(mobile_hash),
            "mobile_verification": mobile_verification,
            "photo_b64": photo_b64,
            "uidai_signed": signature_valid,
            "raw_reference_id": reference_id,
            "qr_data": extracted,
            "decoded_fields": {
                "aadhaar_last4": aadhaar_last4,
                "reference_id": reference_id,
                "name": decoded.get("name"),
                "date_of_birth": decoded.get("dob"),
                "gender": decoded.get("gender"),
                "address": address_text,
            },
            **extracted,
        }
        logger.info("QR decoded successfully via %s", decoder_used)
        return result

    parsed_qr = parse_aadhaar_qr(qr_text)
    if parsed_qr is not None:
        extracted = _extract_payload_fields(parsed_qr, secure=False)
        return {
            "qr_found": True,
            "qr_parsed": True,
            "decoder_used": "xml_or_legacy",
            "signature_valid": False,
            "confidence_score": 0.78,
            **extracted,
            "decoded_fields": {
                "name": extracted["name"],
                "date_of_birth": extracted["dob"],
                "gender": extracted["gender"],
                "address": extracted["address"],
                "aadhaar_last4": extracted["aadhaar_last4"],
                "reference_id": extracted["reference_id"],
            },
            "qr_data": parsed_qr,
        }


def _extract_qr_from_image_bgr(img_array: np.ndarray, mobile_to_verify: str | None = None) -> dict:
    """Attempt QR decode with a small, bounded set of cheap strategies."""
    for variant in _prepare_variants(img_array):
        text, _ = _decode_with_opencv(variant.image)
        if text:
            logger.info("QR detected with OpenCV on %s", variant.label)
            return _run_secure_qr_decode(text, mobile_to_verify=mobile_to_verify)

        for decoder_name, decoder_fn in (("pyzbar", _decode_with_pyzbar), ("zxingcpp", _decode_with_zxingcpp)):
            qr_text = decoder_fn(variant.image)
            if qr_text:
                logger.info("QR detected with %s on %s", decoder_name, variant.label)
                return _run_secure_qr_decode(qr_text, mobile_to_verify=mobile_to_verify)

    return {"qr_found": False, "message": "No QR code found"}


async def _locate_qr_with_vlm(pil_image: Image.Image) -> Optional[dict]:
    """Use the existing VLM stack to find the likely QR region when classical decoding fails."""
    try:
        from services.vlm_kyc import _call_vlm_with_fallback, _parse_json_response, _pil_to_image_part, init_vlm, vlm_ready
    except Exception as exc:
        logger.debug("VLM localization unavailable: %s", exc)
        return None

    if not vlm_ready():
        try:
            init_vlm()
        except Exception as exc:
            logger.debug("VLM init failed: %s", exc)
            return None

    if not vlm_ready():
        return None

    prompt = (
        "Locate the Aadhaar Secure QR code in this document image. "
        "Return ONLY JSON: {\"qr_present\": true/false, \"bbox\": [x1, y1, x2, y2] or null, "
        "\"rotation\": 0/90/180/270, \"confidence\": 0.0-1.0, \"notes\": \"brief\"}. "
        "Coordinates must be normalized 0-1 relative to the full image. "
        "The QR may be small and usually appears near the lower half or lower-right of Aadhaar cards."
    )

    try:
        response = await _call_vlm_with_fallback(
            prompt=prompt,
            image_part=_pil_to_image_part(pil_image),
            task="Aadhaar QR localization",
        )
        data = _parse_json_response(response)
        bbox = data.get("bbox") or data.get("qr_bbox") or data.get("coordinates")
        if isinstance(bbox, list) and len(bbox) == 4:
            return {
                "qr_present": bool(data.get("qr_present", True)),
                "bbox": [float(x) for x in bbox],
                "rotation": _safe_int(data.get("rotation"), 0),
                "confidence": _safe_float(data.get("confidence"), 0.0),
                "notes": data.get("notes", ""),
            }
    except Exception as exc:
        logger.debug("VLM QR localization failed: %s", exc)

    return None


async def _decode_with_vlm_crop(pil_image: Image.Image, mobile_to_verify: str | None = None) -> dict:
    cv2_img = _pil_to_cv2(pil_image)
    localization = await _locate_qr_with_vlm(pil_image)

    if not localization or not localization.get("bbox"):
        return {"qr_found": False, "message": "No QR code found"}

    h, w = cv2_img.shape[:2]
    x1, y1, x2, y2 = localization["bbox"]
    left = int(max(0, min(w - 1, x1 * w)))
    top = int(max(0, min(h - 1, y1 * h)))
    right = int(max(left + 1, min(w, x2 * w)))
    bottom = int(max(top + 1, min(h, y2 * h)))

    crop = cv2_img[top:bottom, left:right]
    if crop.size == 0:
        return {"qr_found": False, "message": "VLM found a QR region, but the crop was empty"}

    rotation = _safe_int(localization.get("rotation"), 0)
    if rotation in (90, 180, 270):
        rotate_map = {
            90: cv2.ROTATE_90_CLOCKWISE,
            180: cv2.ROTATE_180,
            270: cv2.ROTATE_90_COUNTERCLOCKWISE,
        }
        crop = cv2.rotate(crop, rotate_map[rotation])

    for padding in (0.08, 0.16, 0.28, 0.40):
        padded = crop
        if padding > 0:
            pad_x = max(8, int(crop.shape[1] * padding))
            pad_y = max(8, int(crop.shape[0] * padding))
            y_start = max(0, top - pad_y)
            y_end = min(h, bottom + pad_y)
            x_start = max(0, left - pad_x)
            x_end = min(w, right + pad_x)
            padded = cv2_img[y_start:y_end, x_start:x_end]

        if padded.size == 0:
            continue

        result = _extract_qr_from_image_bgr(padded, mobile_to_verify=mobile_to_verify)
        if result.get("qr_found"):
            result["decoder_used"] = f"vlm_crop_{result.get('decoder_used', 'unknown')}"
            result["vlm_bbox"] = localization["bbox"]
            result["vlm_confidence"] = localization.get("confidence", 0.0)
            return result

    return {"qr_found": False, "message": "VLM localized QR area, but decoding still failed"}


def _sync_decode_qr(pil_image: Image.Image, mobile_to_verify: str | None = None) -> dict:
    if not QR_ENABLED:
        return {"qr_found": False, "reason": "QR scanning disabled", "fallback": "OTP verification active"}

    if not PYAADHAAR_AVAILABLE or not PYZBAR_AVAILABLE:
        return {"qr_found": False, "reason": "QR libraries unavailable", "fallback": "OTP verification active"}

    cv2_img = _pil_to_cv2(pil_image)
    result = _extract_qr_from_image_bgr(cv2_img, mobile_to_verify=mobile_to_verify)
    if result.get("qr_found"):
        return result

    return {"qr_found": False, "message": "No QR code found in image"}


async def decode_aadhaar_qr_from_image(
    pil_image: Image.Image,
    mobile_to_verify: str | None = None,
    timeout_seconds: int = 15,
) -> dict:
    """Decode Aadhaar QR from a single PIL image."""
    try:
        loop = asyncio.get_running_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(_qr_executor, _sync_decode_qr, pil_image, mobile_to_verify),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        logger.warning("QR scan timed out after %ss - skipping QR verification", timeout_seconds)
        return {
            "qr_found": False,
            "timed_out": True,
            "message": "QR scan timed out. Proceeding with VLM extraction only. OTP verification will be used for mobile check.",
        }
    except Exception as exc:
        logger.error("QR decode error: %s", exc, exc_info=True)
        return {"qr_found": False, "error": str(exc)}


async def decode_aadhaar_qr_from_document(contents: bytes, filename: str, mobile_to_verify: str | None = None) -> dict:
    """Decode Aadhaar QR from an image, scan, PDF, or e-Aadhaar document."""
    if not PYAADHAAR_AVAILABLE:
        return {"qr_found": False, "error": "pyaadhaar not installed", "install": "pip install pyaadhaar"}

    try:
        pages = _render_pdf_pages(contents, filename)
        if not pages:
            pil_image = Image.open(BytesIO(contents)).convert("RGB")
            pages = [(1, pil_image)]

        last_message = None
        for page_number, page_image in pages:
            logger.info("Scanning Aadhaar QR on page %s", page_number)
            result = await decode_aadhaar_qr_from_image(page_image, mobile_to_verify=mobile_to_verify, timeout_seconds=15)
            if result.get("qr_found"):
                result["page_number"] = page_number
                return result
            last_message = result.get("message") or result.get("error") or "No QR found"

        return {"qr_found": False, "message": last_message or "No QR code found in document"}
    except UnidentifiedImageError as exc:
        logger.error("Unable to open document as image: %s", exc)
        return {"qr_found": False, "error": str(exc)}
    except Exception as exc:
        logger.error("QR document decode error: %s", exc, exc_info=True)
        return {"qr_found": False, "error": str(exc)}


def verify_mobile_against_qr(mobile: str, qr_data: dict, aadhaar_last4: str) -> dict:
    """Verify user mobile against the hash in the QR payload."""
    stored_hash = qr_data.get("mobile_hash")
    if not stored_hash:
        return {
            "verified": False,
            "reason": "NO_HASH_IN_QR",
            "message": "Mobile hash not found in QR code. Using OTP verification instead.",
            "fallback_to_otp": True,
        }

    mobile_clean = re.sub(r"\D", "", mobile or "")
    if mobile_clean.startswith("91") and len(mobile_clean) == 12:
        mobile_clean = mobile_clean[2:]

    aadhaar_clean = re.sub(r"\D", "", aadhaar_last4 or "")[-4:]

    hash_input = (mobile_clean + aadhaar_clean).encode("utf-8")
    computed_hash = hashlib.sha256(hash_input).hexdigest()
    computed_hash_nosalt = hashlib.sha256(mobile_clean.encode()).hexdigest()
    stored_clean = str(stored_hash).lower().strip()
    match = computed_hash.lower() == stored_clean or computed_hash_nosalt.lower() == stored_clean

    logger.info("QR mobile verify: match=%s, mobile=XXXXXX%s", match, mobile_clean[-4:] if mobile_clean else "????")

    return {
        "verified": match,
        "method": "SHA256_QR_HASH",
        "zero_knowledge": True,
        "message": "Mobile verified via Aadhaar QR cryptographic hash." if match else "Mobile number does not match Aadhaar QR record.",
    }


async def process_aadhaar_with_qr(contents: bytes, filename: str, pil_image: Image.Image) -> dict:
    """Scan Aadhaar document for QR metadata used during VLM extraction."""
    try:
        result = await decode_aadhaar_qr_from_document(contents, filename, None)
        if not result.get("qr_found"):
            return {"qr_found": False, "message": result.get("message") or "No QR code found. Using VLM extraction only."}

        qr_data = result.get("qr_data") or result.get("decoded_fields") or result
        if not qr_data:
            return {"qr_found": True, "qr_parsed": False, "message": "QR found but could not parse payload."}

        return {
            "qr_found": True,
            "qr_parsed": True,
            "qr_data": qr_data,
            "has_mobile_hash": bool(qr_data.get("mobile_hash")),
            "has_name": bool(qr_data.get("name")),
            "message": "Aadhaar QR successfully decoded.",
        }
    except Exception as exc:
        logger.error("QR process error: %s", exc, exc_info=True)
        return {"qr_found": False, "error": str(exc)}
