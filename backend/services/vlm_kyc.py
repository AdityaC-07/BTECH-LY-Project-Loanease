import base64
import json
import re
import os
import fitz  # pymupdf
import logging
import asyncio
from PIL import Image
from io import BytesIO
from typing import Optional

from core.config import settings

logger = logging.getLogger("vlm_kyc")

_bedrock_client = None
_primary_model_id: Optional[str] = None
_fallback_model_id: Optional[str] = None
_gemini_primary = None
_gemini_fallback = None
_vlm_provider: str = "bedrock"


def init_vlm():
    global _bedrock_client, _primary_model_id, _fallback_model_id
    global _gemini_primary, _gemini_fallback, _vlm_provider

    _vlm_provider = (settings.VLM_PROVIDER or os.getenv("VLM_PROVIDER", "bedrock")).lower()
    primary = settings.VLM_PRIMARY or os.getenv("VLM_PRIMARY", "us.meta.llama3-2-11b-instruct-v1:0")
    fallback = settings.VLM_FALLBACK or os.getenv("VLM_FALLBACK", primary)

    if _vlm_provider == "bedrock":
        import boto3

        region = settings.AWS_REGION or os.getenv("AWS_REGION", "us-east-1")
        access_key = (settings.AWS_ACCESS_KEY_ID or os.getenv("AWS_ACCESS_KEY_ID") or "").strip()
        secret_key = (settings.AWS_SECRET_ACCESS_KEY or os.getenv("AWS_SECRET_ACCESS_KEY") or "").strip()

        if access_key and secret_key:
            _bedrock_client = boto3.client(
                "bedrock-runtime",
                region_name=region,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
            )
        else:
            # Fall back to AWS CLI profile / instance role credentials
            session = boto3.Session(region_name=region)
            creds = session.get_credentials()
            if creds is None:
                raise ValueError(
                    "AWS credentials not found. Set AWS_ACCESS_KEY_ID and "
                    "AWS_SECRET_ACCESS_KEY in backend/.env (quote values that contain +), "
                    "or run `aws configure`."
                )
            _bedrock_client = session.client("bedrock-runtime")
        _primary_model_id = primary
        _fallback_model_id = fallback
        _gemini_primary = None
        _gemini_fallback = None
        logger.info(
            "VLM KYC initialized (Bedrock): region=%s, primary=%s, fallback=%s",
            region,
            primary,
            fallback,
        )
        return

    import google.generativeai as genai

    api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in .env")

    genai.configure(api_key=api_key)
    _gemini_primary = genai.GenerativeModel(primary)
    _gemini_fallback = genai.GenerativeModel(fallback)
    _bedrock_client = None
    _primary_model_id = None
    _fallback_model_id = None
    logger.info("VLM KYC initialized (Gemini): primary=%s, fallback=%s", primary, fallback)


def vlm_ready() -> bool:
    if _vlm_provider == "bedrock":
        return _bedrock_client is not None
    return _gemini_primary is not None


def _model_label() -> str:
    return "bedrock-llama-vlm" if _vlm_provider == "bedrock" else "gemini-vlm"


# Compatibility aliases for drop-in migration from services.ocr
init_ocr = init_vlm
ocr_ready = vlm_ready


def _file_to_pil(contents: bytes, filename: str) -> Image.Image:
    """
    Convert any uploaded file to PIL Image for Gemini.
    Handles JPG, PNG, PDF.
    """
    fname = filename.lower()

    if fname.endswith(".pdf"):
        doc = fitz.open(stream=contents, filetype="pdf")
        page = doc[0]
        # Render at 2x for better VLM reading
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        doc.close()
        return Image.open(BytesIO(img_bytes))

    elif fname.endswith((".jpg", ".jpeg", ".png", ".bmp")):
        return Image.open(BytesIO(contents))

    else:
        raise ValueError(f"Unsupported file: {filename}")


def _pil_to_image_part(img: Image.Image) -> dict:
    """Convert PIL image to a provider-neutral image payload."""
    max_dim = 1600
    w, h = img.size
    if max(w, h) > max_dim:
        ratio = max_dim / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    if img.mode != "RGB":
        img = img.convert("RGB")

    if _vlm_provider == "bedrock":
        buf = BytesIO()
        img.save(buf, format="PNG")
        return {"format": "png", "bytes": buf.getvalue()}

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=95)
    img_bytes = buf.getvalue()
    return {
        "mime_type": "image/jpeg",
        "data": base64.b64encode(img_bytes).decode(),
    }


# ─── PAN CARD EXTRACTION ────────────────

PAN_PROMPT = """
You are a KYC document extraction system for an Indian lending platform.

Analyze this PAN card image and extract the following fields with MAXIMUM accuracy.

PAN cards are issued by the Indian Income Tax Department and contain:
- PAN Number (format: 5 uppercase letters + 4 digits + 1 uppercase letter, e.g. ABCDE1234F)
- Name of cardholder (in English, usually all caps)
- Father's Name (in English, usually below the cardholder name)
- Date of Birth (format DD/MM/YYYY)

IMPORTANT EXTRACTION RULES:
1. PAN number: Look for the 10-character alphanumeric code. It appears prominently on the card. Common OCR mistakes: O vs 0, I vs 1, l vs 1. Positions 6-9 must be digits. Position 10 must be a letter.
2. Name: Usually printed in CAPITAL LETTERS. Exclude the label "Name" itself.
3. Father's Name: Line labeled "Father's Name" or "S/O" or "D/O".
4. DOB: Look for "Date of Birth" or "DOB" label. Format DD/MM/YYYY. If you see "15 AUG 1995" convert to "15/08/1995".

Respond ONLY with this exact JSON. No explanation, no markdown, just JSON:
{
  "pan_number": "XXXXX9999X or null",
  "name": "FULL NAME or null",
  "fathers_name": "FATHERS NAME or null",
  "date_of_birth": "DD/MM/YYYY or null",
  "age": <integer or null>,
  "document_type_confirmed": true/false,
  "confidence": <0.0 to 1.0>,
  "extraction_notes": "any issues noticed"
}

If this is not a PAN card, set document_type_confirmed to false and all fields to null.
"""


async def extract_pan(contents: bytes, filename: str) -> dict:
    """Extract PAN card fields using Gemini VLM."""
    logger.info(f"VLM PAN extraction: {filename} ({len(contents)} bytes)")

    try:
        img = _file_to_pil(contents, filename)
        img_part = _pil_to_image_part(img)

        result = await _call_vlm_with_fallback(
            prompt=PAN_PROMPT,
            image_part=img_part,
            task="PAN extraction",
        )

        data = _parse_json_response(result)
        return _validate_pan_data(data)

    except RuntimeError as e:
        # VLM provider failed - log the error context
        error_msg = str(e)
        logger.error(f"PAN extraction provider error: {error_msg}")
        
        # Check if it's an IAM/auth issue
        if "not authorized" in error_msg.lower() or "accessdenied" in error_msg.lower():
            logger.critical("IAM permission error detected - check AWS credentials and IAM policy")
        
        return {
            "success": False,
            "error": error_msg,
            "pan_number": None,
            "name": None,
        }
    except Exception as e:
        # Other errors (image processing, parsing, validation)
        error_type = type(e).__name__
        error_msg = str(e)
        logger.error(f"PAN extraction error ({error_type}): {error_msg}", exc_info=True)
        return {
            "success": False,
            "error": f"{error_type}: {error_msg}",
            "pan_number": None,
            "name": None,
        }


def _validate_pan_data(data: dict) -> dict:
    """Validate and clean VLM-extracted PAN data."""
    pan = data.get("pan_number")
    issues = []

    if pan:
        pan = pan.upper().replace(" ", "")
        pan_list = list(pan)
        for i in range(5, 9):
            if i < len(pan_list):
                if pan_list[i] == "O":
                    pan_list[i] = "0"
                if pan_list[i] in ("I", "l"):
                    pan_list[i] = "1"
        pan = "".join(pan_list)

        if not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", pan):
            issues.append(f"PAN format invalid: {pan}")
            pan = None
    else:
        issues.append("PAN number not found")

    dob = data.get("date_of_birth")
    age = data.get("age")
    age_eligible = None

    if dob and not age:
        try:
            from datetime import datetime

            for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"]:
                try:
                    dt = datetime.strptime(dob, fmt)
                    age = (datetime.now() - dt).days // 365
                    break
                except ValueError:
                    continue
        except Exception:
            pass

    if age:
        age_eligible = 21 <= age <= 65
        if not age_eligible:
            issues.append(f"Age {age} not eligible (must be 21-65)")

    return {
        "success": pan is not None,
        "document_type": "PAN",
        "extracted_fields": {
            "pan_number": pan,
            "name": data.get("name"),
            "fathers_name": data.get("fathers_name"),
            "date_of_birth": dob,
            "age": age,
            "age_eligible": age_eligible,
        },
        "validation": {
            "overall_valid": pan is not None and not issues,
            "pan_format_valid": pan is not None,
            "age_check_passed": age_eligible,
            "issues": issues,
        },
        "confidence_score": data.get("confidence", 0.0),
        "vlm_notes": data.get("extraction_notes", ""),
        "model_used": _model_label(),
    }


# ─── AADHAAR EXTRACTION ─────────────────

AADHAAR_PROMPT = """
You are a KYC document extraction system for an Indian lending platform.

Analyze this Aadhaar card image carefully.
Aadhaar cards are issued by UIDAI (Unique Identification Authority of India).

Extract these fields:

1. Aadhaar Number: 12 digits, usually printed as XXXX XXXX XXXX. Never starts with 0 or 1.

2. Name: Cardholder's full name (in English, may be mixed case).

3. Date of Birth OR Year of Birth: Some Aadhaar cards show full DOB (DD/MM/YYYY), others show just Year of Birth (YYYY).

4. Gender: Male/Female/Transgender. Look for "पुरुष"=Male, "महिला"=Female in Hindi.

5. Address: Full address including house number, street, city, state, pincode. This is CRITICAL for mobile number extraction.

6. Mobile Number: 10-digit Indian mobile number. It may appear in the address section or near it. MUST start with 6, 7, 8, or 9. Look carefully — it's often in small text near the address.

7. VID (Virtual ID): 16-digit number if present (optional).

IMPORTANT:
- This may be the front side (photo + basic details) OR back side (address + barcode) of the card.
- If it's the back side, focus on extracting address and mobile number.
- If it's a digital Aadhaar (PDF format), both sides may be visible.

Respond ONLY with this exact JSON:
{
  "aadhaar_number": "12 digits no spaces, or null",
  "aadhaar_last4": "last 4 digits or null",
  "name": "Full Name or null",
  "date_of_birth": "DD/MM/YYYY or null",
  "year_of_birth": <YYYY integer or null>,
  "age": <integer or null>,
  "gender": "Male/Female/Other or null",
  "address": {
    "full": "complete address or null",
    "pincode": "6 digits or null",
    "city": "city name or null",
    "state": "state name or null"
  },
  "mobile_number": "10 digits or null",
  "vid": "16 digits or null",
  "card_side": "front/back/both/unknown",
  "document_type_confirmed": true/false,
  "confidence": <0.0 to 1.0>,
  "extraction_notes": "any issues"
}
"""


async def extract_aadhaar(contents: bytes, filename: str) -> dict:
    """Extract Aadhaar card fields using Gemini VLM."""
    logger.info(f"VLM Aadhaar extraction: {filename} ({len(contents)} bytes)")

    try:
        img = _file_to_pil(contents, filename)
        img_part = _pil_to_image_part(img)

        result = await _call_vlm_with_fallback(
            prompt=AADHAAR_PROMPT,
            image_part=img_part,
            task="Aadhaar extraction",
        )

        data = _parse_json_response(result)
        return _validate_aadhaar_data(data)

    except RuntimeError as e:
        # VLM provider failed
        error_msg = str(e)
        logger.error(f"Aadhaar extraction provider error: {error_msg}")
        
        if "not authorized" in error_msg.lower() or "accessdenied" in error_msg.lower():
            logger.critical("IAM permission error detected - check AWS credentials and IAM policy")
        
        return {
            "success": False,
            "error": error_msg,
        }
    except Exception as e:
        # Other errors
        error_type = type(e).__name__
        error_msg = str(e)
        logger.error(f"Aadhaar extraction error ({error_type}): {error_msg}", exc_info=True)
        return {
            "success": False,
            "error": f"{error_type}: {error_msg}",
        }


def _validate_aadhaar_data(data: dict) -> dict:
    issues = []

    aadhaar = data.get("aadhaar_number")
    if aadhaar:
        aadhaar = re.sub(r"\s", "", str(aadhaar))
        if not re.match(r"^[2-9]\d{11}$", aadhaar):
            issues.append("Aadhaar format invalid")
            aadhaar = None

    last4 = aadhaar[-4:] if aadhaar else data.get("aadhaar_last4")

    age = data.get("age")
    dob = data.get("date_of_birth")
    yob = data.get("year_of_birth")
    age_eligible = None

    if not age:
        if dob:
            try:
                from datetime import datetime

                dt = datetime.strptime(dob, "%d/%m/%Y")
                age = (datetime.now() - dt).days // 365
            except Exception:
                pass
        elif yob:
            from datetime import datetime

            age = datetime.now().year - yob

    if age:
        age_eligible = 21 <= age <= 65

    mobile = data.get("mobile_number")
    if mobile:
        mobile = re.sub(r"\D", "", str(mobile))
        if mobile.startswith("91") and len(mobile) == 12:
            mobile = mobile[2:]
        if not (len(mobile) == 10 and mobile[0] in "6789"):
            logger.warning(f"Invalid mobile: {mobile}")
            mobile = None

    mobile_last4 = mobile[-4:] if mobile else None

    return {
        "success": True,
        "document_type": "AADHAAR",
        "card_side": data.get("card_side", "unknown"),
        "extracted_fields": {
            "aadhaar_last4": last4,
            "aadhaar_number": aadhaar,
            "name": data.get("name"),
            "date_of_birth": dob,
            "year_of_birth": yob,
            "age": age,
            "age_eligible": age_eligible,
            "gender": data.get("gender"),
            "address": data.get("address", {}),
            "mobile_number": mobile,
            "mobile_last4": mobile_last4,
            "mobile_found": mobile is not None,
        },
        "validation": {
            "overall_valid": True,
            "aadhaar_format_valid": aadhaar is not None,
            "mobile_found": mobile is not None,
            "age_eligible": age_eligible,
            "issues": issues,
        },
        "confidence_score": data.get("confidence", 0.0),
        "model_used": _model_label(),
    }


# ─── CROSS VALIDATION ───────────────────

CROSS_VALIDATE_PROMPT = """
Compare these two sets of KYC data extracted from a PAN card and Aadhaar card:

PAN Data: {pan_data}
Aadhaar Data: {aadhaar_data}

Determine if these documents belong to the same person.

Check:
1. Name similarity (account for abbreviations, middle names, spelling variations — "AGNIV DUTTA" vs "Agniv Dutta" is a MATCH)
2. Date of birth match (if both have full DOB)
3. Year of birth match (if Aadhaar only has year)

Respond ONLY with JSON:
{
  "same_person": true/false,
  "name_match": true/false,
  "name_similarity": <0.0 to 1.0>,
  "pan_name": "name from PAN",
  "aadhaar_name": "name from Aadhaar",
  "dob_match": true/false/null,
  "overall_kyc_status": "VERIFIED/PARTIAL/FAILED",
  "confidence": <0.0 to 1.0>,
  "reasoning": "brief explanation"
}
"""


async def cross_validate(pan_data: dict, aadhaar_data: dict) -> dict:
    """
    Use VLM intelligence to cross-validate PAN and Aadhaar data.
    Handles name variations better than fuzzy string matching.
    """
    try:
        pan_fields = pan_data.get("extracted_fields", pan_data)
        aadhaar_fields = aadhaar_data.get("extracted_fields", aadhaar_data)

        prompt = CROSS_VALIDATE_PROMPT.format(
            pan_data=json.dumps(
                {
                    "name": pan_fields.get("name"),
                    "dob": pan_fields.get("date_of_birth"),
                    "pan": pan_fields.get("pan_number"),
                }
            ),
            aadhaar_data=json.dumps(
                {
                    "name": aadhaar_fields.get("name"),
                    "dob": aadhaar_fields.get("date_of_birth"),
                    "yob": aadhaar_fields.get("year_of_birth"),
                }
            ),
        )

        result = await _call_vlm_with_fallback(
            prompt=prompt,
            image_part=None,
            task="Cross validation",
        )

        data = _parse_json_response(result)
        status = data.get("overall_kyc_status", "FAILED")

        return {
            "kyc_status": status,
            "same_person": data.get("same_person", False),
            "name_match": data.get("name_match", False),
            "name_similarity": data.get("name_similarity", 0.0),
            "pan_name": data.get("pan_name"),
            "aadhaar_name": data.get("aadhaar_name"),
            "dob_match": data.get("dob_match"),
            "confidence": data.get("confidence", 0.0),
            "reasoning": data.get("reasoning", ""),
            "overall_kyc_passed": status == "VERIFIED",
        }

    except Exception as e:
        logger.error(f"Cross-validation error: {e}")
        pan_fields = pan_data.get("extracted_fields", pan_data)
        aad_fields = aadhaar_data.get("extracted_fields", aadhaar_data)
        pan_name = pan_fields.get("name", "")
        aad_name = aad_fields.get("name", "")

        match = pan_name.lower() in aad_name.lower() or aad_name.lower() in pan_name.lower()

        return {
            "kyc_status": "VERIFIED" if match else "FAILED",
            "same_person": match,
            "name_match": match,
            "name_similarity": 1.0 if match else 0.0,
            "overall_kyc_passed": match,
            "fallback_used": True,
        }


def map_cross_validation_to_legacy(vlm_result: dict, pan_data: dict, aadhaar_data: dict) -> dict:
    """Map VLM cross-validation output to the legacy response schema."""
    name_similarity = float(vlm_result.get("name_similarity") or 0.0)
    name_score = int(round(name_similarity * 100)) if name_similarity <= 1.0 else int(name_similarity)

    if vlm_result.get("name_match"):
        name_status = "MATCH"
    elif name_score >= 45:
        name_status = "PARTIAL"
    else:
        name_status = "MISMATCH"

    kyc_status = vlm_result.get("kyc_status", "FAILED")
    age_eligible = pan_data.get("age_eligible", True) or aadhaar_data.get("age_eligible", True)

    if kyc_status == "VERIFIED":
        overall_passed = True
    elif kyc_status == "PARTIAL":
        overall_passed = True
    else:
        overall_passed = name_score >= 35 and age_eligible

    return {
        "kyc_status": kyc_status,
        "name_match_score": name_score,
        "name_match_status": name_status,
        "dob_match": bool(vlm_result.get("dob_match")),
        "age_eligible": age_eligible,
        "overall_kyc_passed": overall_passed,
    }


# ─── VLM CALL WITH FALLBACK ─────────────

def _extract_response_text(response: dict) -> str:
    content = response.get("output", {}).get("message", {}).get("content", [])
    parts = []
    for block in content:
        if "text" in block:
            parts.append(block["text"])
    return "\n".join(parts).strip()


def _call_bedrock_converse(model_id: str, prompt: str, image_part: Optional[dict]) -> str:
    content = [{"text": prompt}]
    if image_part:
        content = [
            {
                "image": {
                    "format": image_part["format"],
                    "source": {"bytes": image_part["bytes"]},
                }
            },
            {"text": prompt},
        ]

    try:
        logger.debug(f"Calling Bedrock model {model_id} with {len(content)} content parts")
        response = _bedrock_client.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": content}],
            inferenceConfig={
                "maxTokens": 2048,
                "temperature": 0.1,
            },
        )
        return _extract_response_text(response)
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        logger.error(f"Bedrock call failed: {error_type} - {error_msg}")
        
        # Re-raise with context for upstream handlers
        if "AccessDenied" in error_type or "not authorized" in error_msg.lower():
            logger.error(f"IAM Permission issue: Check that loanease-bedrock has bedrock:Converse permission")
        raise


def _call_gemini_converse(prompt: str, image_part: Optional[dict], model) -> str:
    if image_part:
        content = [
            {
                "role": "user",
                "parts": [
                    {"inline_data": image_part},
                    {"text": prompt},
                ],
            }
        ]
    else:
        content = [{"role": "user", "parts": [{"text": prompt}]}]

    response = model.generate_content(content)
    return response.text


async def _call_vlm_with_fallback(
    prompt: str,
    image_part: Optional[dict],
    task: str,
) -> str:
    """Call primary VLM model. Fall back to secondary on failure."""
    timeout = settings.VLM_TIMEOUT or int(os.getenv("VLM_TIMEOUT", "60"))
    errors = []

    if _vlm_provider == "bedrock":
        for label, model_id in (("primary", _primary_model_id), ("fallback", _fallback_model_id)):
            try:
                logger.info(f"VLM {task}: Trying {label} Bedrock model ({model_id})")
                result = await asyncio.wait_for(
                    asyncio.to_thread(_call_bedrock_converse, model_id, prompt, image_part),
                    timeout=timeout,
                )
                logger.info(f"VLM {task}: {label} model success")
                return result
            except asyncio.TimeoutError:
                msg = f"VLM {task}: {label} timeout after {timeout}s"
                logger.warning(msg)
                errors.append(msg)
            except Exception as exc:
                error_type = type(exc).__name__
                msg = f"VLM {task}: {label} failed ({error_type}: {exc})"
                logger.error(msg)
                errors.append(msg)
        
        error_summary = " | ".join(errors)
        raise RuntimeError(f"Bedrock VLM failed for task: {task}. Details: {error_summary}")

    for label, model in (("primary", _gemini_primary), ("fallback", _gemini_fallback)):
        try:
            logger.info(f"VLM {task}: Trying {label} Gemini model")
            result = await asyncio.wait_for(
                asyncio.to_thread(_call_gemini_converse, prompt, image_part, model),
                timeout=timeout,
            )
            logger.info(f"VLM {task}: {label} model success")
            return result
        except asyncio.TimeoutError:
            msg = f"VLM {task}: {label} timeout after {timeout}s"
            logger.warning(msg)
            errors.append(msg)
        except Exception as exc:
            error_type = type(exc).__name__
            msg = f"VLM {task}: {label} failed ({error_type}: {exc})"
            logger.error(msg)
            errors.append(msg)

    error_summary = " | ".join(errors)
    raise RuntimeError(f"Gemini VLM failed for task: {task}. Details: {error_summary}")


def _parse_json_response(text: str) -> dict:
    """Robustly parse JSON from VLM response. VLMs sometimes wrap JSON in markdown."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse failed: {e}\nText: {text[:300]}")
        return {}
