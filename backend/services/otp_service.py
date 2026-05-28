import logging
import os

from fastapi import HTTPException
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

logger = logging.getLogger("otp")

_client = None
_service_sid = None
_demo_store: dict[str, str] = {}


def _verify_payload(
    *,
    session_id: str,
    verified: bool,
    mobile: str,
    attempts_remaining: int,
    terminated: bool = False,
    reason: str | None = None,
    message: str | None = None,
    method: str | None = None,
    zero_knowledge: bool | None = None,
    demo_mode: bool | None = None,
    twilio_status: str | None = None,
) -> dict:
    payload = {
        "session_id": session_id,
        "verified": verified,
        "terminated": terminated,
        "attempts_remaining": attempts_remaining,
        "mobile_last4": mobile[-4:],
        "expires_in_seconds": 600,
        "reason": reason,
        "message": message,
        "method": method,
        "zero_knowledge": zero_knowledge,
    }

    if demo_mode is not None:
        payload["demo_mode"] = demo_mode
    if twilio_status is not None:
        payload["twilio_status"] = twilio_status

    return payload


def init_twilio() -> bool:
    global _client, _service_sid

    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    _service_sid = os.getenv("TWILIO_VERIFY_SERVICE_SID")

    if not all([sid, token, _service_sid]):
        logger.warning("Twilio not configured - OTP will run in demo mode only")
        return False

    _client = Client(sid, token)
    logger.info("Twilio Verify ready")
    return True


def twilio_ready() -> bool:
    return _client is not None and _service_sid is not None


def _format_india_number(mobile: str) -> str:
    """
    Format mobile number for Twilio.
    Twilio requires E.164 format: +91XXXXXXXXXX
    """
    digits = "".join(c for c in mobile if c.isdigit())

    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]

    if len(digits) != 10 or digits[0] not in "6789":
        raise ValueError(f"Invalid Indian mobile: {mobile}")

    return f"+91{digits}"


async def send(session_id: str, mobile: str) -> dict:
    """
    Send OTP via Twilio Verify.
    Twilio handles OTP generation, storage, expiry, and retry automatically.
    """
    demo_mode = os.getenv("DEMO_MODE", "false").lower() == "true"

    if demo_mode or not twilio_ready():
        import random

        demo_otp = str(random.randint(100000, 999999))
        _demo_store[session_id] = demo_otp

        logger.info("DEMO OTP [%s]: %s", session_id, demo_otp)

        return {
            "session_id": session_id,
            "sent": True,
            "mobile_last4": mobile[-4:],
            "expires_in_seconds": 600,
            "demo_mode": True,
            "demo_otp": demo_otp,
            "message": f"Demo mode active. Your OTP: {demo_otp}",
        }

    try:
        e164 = _format_india_number(mobile)
        verification = _client.verify.v2.services(_service_sid).verifications.create(
            to=e164,
            channel="sms",
        )

        logger.info(
            "OTP sent via Twilio: status=%s, to=+91XXXXXX%s",
            verification.status,
            mobile[-4:],
        )

        return {
            "session_id": session_id,
            "sent": True,
            "mobile_last4": mobile[-4:],
            "expires_in_seconds": 600,
            "twilio_status": verification.status,
            "message": f"OTP sent to mobile ending in {mobile[-4:]}. Valid for 10 minutes.",
        }

    except TwilioRestException as exc:
        logger.error("Twilio error: code=%s, msg=%s", exc.code, exc.msg)

        error_messages = {
            60200: "Invalid phone number format",
            60203: "Max send attempts reached. Wait 10 minutes.",
            60212: "Too many concurrent requests",
            21608: "Number not verified (trial account restriction). Use a verified number.",
        }

        user_message = error_messages.get(exc.code, "SMS delivery failed. Please check your number.")

        import random

        fallback_otp = str(random.randint(100000, 999999))
        _demo_store[session_id] = fallback_otp

        return {
            "session_id": session_id,
            "sent": False,
            "mobile_last4": mobile[-4:],
            "error_code": exc.code,
            "message": user_message,
            "fallback_demo_otp": fallback_otp,
            "demo_otp": fallback_otp,
            "fallback_active": True,
        }

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def verify(session_id: str, entered_otp: str, mobile: str) -> dict:
    """
    Verify OTP via Twilio Verify.
    Twilio checks the OTP, handles expiry and attempt limits automatically.
    """
    demo_mode = os.getenv("DEMO_MODE", "false").lower() == "true"

    if demo_mode or not twilio_ready():
        expected = _demo_store.get(session_id)

        if not expected:
            return _verify_payload(
                session_id=session_id,
                verified=False,
                mobile=mobile,
                attempts_remaining=0,
                reason="NOT_FOUND",
                message="OTP expired. Request a new one.",
                demo_mode=True,
            )

        if entered_otp.strip() == expected:
            _demo_store.pop(session_id, None)
            return _verify_payload(
                session_id=session_id,
                verified=True,
                mobile=mobile,
                attempts_remaining=3,
                message="Mobile verified.",
                demo_mode=True,
            )

        return _verify_payload(
            session_id=session_id,
            verified=False,
            mobile=mobile,
            attempts_remaining=2,
            reason="WRONG_OTP",
            message="Incorrect OTP. Please try again.",
            demo_mode=True,
        )

    try:
        e164 = _format_india_number(mobile)
        check = _client.verify.v2.services(_service_sid).verification_checks.create(
            to=e164,
            code=entered_otp.strip(),
        )

        logger.info("OTP verify: status=%s", check.status)

        if check.status == "approved":
            return _verify_payload(
                session_id=session_id,
                verified=True,
                mobile=mobile,
                attempts_remaining=3,
                message="Mobile number verified successfully.",
                twilio_status=check.status,
            )

        return _verify_payload(
            session_id=session_id,
            verified=False,
            mobile=mobile,
            attempts_remaining=2,
            reason="WRONG_OTP",
            message="Incorrect OTP. Please try again.",
            twilio_status=check.status,
        )

    except TwilioRestException as exc:
        logger.error("Twilio verify error: code=%s", exc.code)

        if exc.code == 60202:
            return _verify_payload(
                session_id=session_id,
                verified=False,
                mobile=mobile,
                attempts_remaining=0,
                terminated=True,
                reason="MAX_ATTEMPTS",
                message="Maximum verification attempts exceeded. Application terminated for security.",
            )

        if exc.code == 60203:
            return _verify_payload(
                session_id=session_id,
                verified=False,
                mobile=mobile,
                attempts_remaining=0,
                reason="EXPIRED",
                message="OTP has expired. Please request a new one.",
            )

        return _verify_payload(
            session_id=session_id,
            verified=False,
            mobile=mobile,
            attempts_remaining=0,
            reason="ERROR",
            message="Verification failed. Please try again.",
        )


async def resend(session_id: str, mobile: str) -> dict:
    """
    Twilio Verify handles rate limiting automatically.
    Just call send() again.
    """
    return await send(session_id, mobile)
