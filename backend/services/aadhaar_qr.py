import base64
import hashlib
import logging
import re
import zlib
from io import BytesIO
from typing import Optional
import xml.etree.ElementTree as ET

import cv2
import numpy as np
from PIL import Image

try:
    from pyzbar import pyzbar

    PYZBAR_AVAILABLE = True
except ImportError:
    PYZBAR_AVAILABLE = False
    logging.warning("pyzbar not available - QR decode disabled")

logger = logging.getLogger("aadhaar_qr")


def _pil_to_cv2(img: Image.Image) -> np.ndarray:
    """Convert PIL image to an OpenCV BGR array."""
    rgb = img.convert("RGB")
    return cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)


def decode_qr_from_image(img_array: np.ndarray) -> Optional[bytes]:
    """
    Find and decode QR code from image.
    Tries multiple preprocessing strategies for robustness.
    """
    if not PYZBAR_AVAILABLE:
        return None

    gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY)
    strategies = [
        img_array,
        gray,
        cv2.equalizeHist(gray),
        cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
    ]

    for index, img in enumerate(strategies, start=1):
        try:
            if len(img.shape) == 2:
                scan_img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            else:
                scan_img = img

            codes = pyzbar.decode(scan_img)
            for code in codes:
                if code.type in ("QRCODE", "QR CODE"):
                    logger.info("QR found with strategy %s: %s bytes", index, len(code.data))
                    return code.data
        except Exception as exc:
            logger.debug("Strategy %s failed: %s", index, exc)
            continue

    logger.info("No QR code found in image")
    return None


def parse_aadhaar_qr(qr_data: bytes) -> Optional[dict]:
    """
    Parse UIDAI Aadhaar QR payload.
    Supports XML payloads, base64-encoded data, and secure QR binary payloads.
    """
    if not qr_data:
        return None

    try:
        text = qr_data.decode("utf-8", errors="ignore") if isinstance(qr_data, bytes) else str(qr_data)
        stripped = text.strip()

        if stripped.startswith("<?xml") or stripped.startswith("<"):
            return _parse_xml_payload(stripped)

        if stripped.isdigit():
            return _parse_secure_qr(int(stripped))

        try:
            decoded = base64.b64decode(stripped)
            parsed = _parse_binary_payload(decoded)
            if parsed:
                return parsed
        except Exception:
            pass

        logger.warning("Unknown QR format: %s", stripped[:50])
        return None

    except Exception as exc:
        logger.error("QR parse error: %s", exc)
        return None


def _parse_secure_qr(big_int: int) -> Optional[dict]:
    """Parse UIDAI Secure QR v2 format."""
    try:
        byte_length = (big_int.bit_length() + 7) // 8
        raw_bytes = big_int.to_bytes(byte_length, byteorder="big")

        try:
            decompressed = zlib.decompress(raw_bytes)
        except Exception:
            try:
                decompressed = zlib.decompress(raw_bytes, -15)
            except Exception:
                decompressed = raw_bytes

        return _parse_binary_payload(decompressed)

    except Exception as exc:
        logger.error("Secure QR parse error: %s", exc)
        return None


def _parse_binary_payload(data: bytes) -> Optional[dict]:
    """Parse binary payload from decompressed QR data."""
    try:
        text = data.decode("utf-8", errors="replace")
        if "<" in text and ">" in text:
            return _parse_xml_payload(text)

        return _parse_fields_from_binary(data)
    except Exception as exc:
        logger.debug("Binary parse: %s", exc)
        return None


def _parse_xml_payload(xml_text: str) -> dict:
    """Parse XML-format Aadhaar QR payload."""
    result: dict[str, object] = {}

    try:
        root = ET.fromstring(xml_text)
        if root is not None:
            attrib = {key.lower(): value for key, value in root.attrib.items()}

            def _first_value(patterns: list[str]) -> Optional[str]:
                for pattern in patterns:
                    match = re.search(pattern, xml_text, re.IGNORECASE)
                    if match:
                        return match.group(1).strip()
                return None

            result["name"] = attrib.get("n") or attrib.get("name") or _first_value([r'name="([^"]+)"', r'n="([^"]+)"'])
            result["dob"] = attrib.get("dob") or attrib.get("yob") or _first_value([r'dob="([^"]+)"', r'yob="([^"]+)"'])
            result["gender"] = attrib.get("g") or attrib.get("gender") or _first_value([r'gender="([^"]+)"', r'g="([^"]+)"'])
            result["mobile_hash"] = attrib.get("mobilehash") or attrib.get("mh") or _first_value([
                r'mobileHash="([^"]+)"',
                r'mh="([^"]+)"',
                r'mobile="([^"]{40,})"',
            ])
            result["email_hash"] = attrib.get("emailhash") or attrib.get("eh") or _first_value([r'emailHash="([^"]+)"', r'eh="([^"]+)"'])

            address = []
            for tag in ("po", "vtc", "dist", "subdist", "state", "pc"):
                value = attrib.get(tag)
                if value:
                    address.append(value)
            if address:
                result["address"] = ", ".join(address)

            result["pincode"] = attrib.get("pc") or _first_value([r'pc="([^"]+)"', r'pincode="([^"]+)"'])
        else:
            result["name"] = None
    except Exception:
        patterns = {
            "name": [r'name="([^"]+)"', r'n="([^"]+)"'],
            "dob": [r'dob="([^"]+)"', r'yob="([^"]+)"'],
            "gender": [r'gender="([^"]+)"', r'g="([^"]+)"'],
            "mobile_hash": [r'mobileHash="([^"]+)"', r'mh="([^"]+)"', r'mobile="([^"]{40,})"'],
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


def _parse_fields_from_binary(data: bytes) -> dict:
    """Attempt to extract fields from binary Aadhaar QR format."""
    try:
        text = data.decode("utf-8", errors="ignore")
        readable = re.findall(r"[A-Za-z0-9@.\s,/-]{4,}", text)

        result = {
            "raw_strings": readable[:20],
            "qr_parsed": True,
            "format": "binary",
        }

        for item in readable:
            value = item.strip()
            if re.match(r"\d{2}[-/]\d{2}[-/]\d{4}", value) or (re.match(r"\d{4}", value) and len(value) == 4):
                result.setdefault("dob", value)
            elif re.match(r"[0-9a-f]{40,}", value.lower()):
                result.setdefault("mobile_hash", value)
            elif len(value) > 5 and all(c.isalpha() or c.isspace() for c in value):
                result.setdefault("name", value)

        return result

    except Exception as exc:
        logger.debug("Binary fields: %s", exc)
        return {"qr_parsed": False}


def verify_mobile_against_qr(mobile: str, qr_data: dict, aadhaar_last4: str) -> dict:
    """
    Verify user-provided mobile number against the SHA-256 hash stored in Aadhaar QR.
    """
    stored_hash = qr_data.get("mobile_hash")

    if not stored_hash:
        return {
            "verified": False,
            "reason": "NO_HASH_IN_QR",
            "message": "Mobile hash not found in QR code. Using OTP verification instead.",
            "fallback_to_otp": True,
        }

    mobile_clean = re.sub(r"\D", "", mobile)
    if mobile_clean.startswith("91") and len(mobile_clean) == 12:
        mobile_clean = mobile_clean[2:]

    aadhaar_clean = re.sub(r"\D", "", aadhaar_last4)[-4:]

    hash_input = (mobile_clean + aadhaar_clean).encode("utf-8")
    computed_hash = hashlib.sha256(hash_input).hexdigest()
    computed_hash_nosalt = hashlib.sha256(mobile_clean.encode()).hexdigest()

    stored_clean = str(stored_hash).lower()
    match = computed_hash.lower() == stored_clean or computed_hash_nosalt.lower() == stored_clean

    logger.info("QR mobile verify: match=%s, mobile=XXXXXX%s", match, mobile_clean[-4:])

    return {
        "verified": match,
        "method": "SHA256_QR_HASH",
        "zero_knowledge": True,
        "message": (
            "Mobile verified via Aadhaar QR cryptographic hash."
            if match
            else "Mobile number does not match Aadhaar QR record."
        ),
    }


async def process_aadhaar_with_qr(contents: bytes, filename: str, pil_image: Image.Image) -> dict:
    """
    Scan Aadhaar image for QR code and parse it.
    Returns QR metadata to supplement VLM extraction.
    """
    try:
        cv2_img = _pil_to_cv2(pil_image)
        qr_raw = decode_qr_from_image(cv2_img)

        if not qr_raw:
            return {"qr_found": False, "message": "No QR code found. Using VLM extraction only."}

        qr_data = parse_aadhaar_qr(qr_raw)
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
        logger.error("QR process error: %s", exc)
        return {"qr_found": False, "error": str(exc)}
