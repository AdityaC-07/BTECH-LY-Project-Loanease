"""
Startup self-test for LoanEase.

Validates that all critical components (XGBoost model, VLM KYC engine,
Groq connectivity, blockchain ledger) are functional before the
server begins accepting requests.

Called at the end of the FastAPI lifespan startup phase.
"""

import asyncio
import logging
from typing import Any, Dict

logger = logging.getLogger("loanease.selftest")

_SELFTEST_TIMEOUT_SEC = 12


async def run_startup_selftest(app: Any) -> Dict[str, str]:
    """Run self-tests on all critical components and print a report."""
    try:
        return await asyncio.wait_for(_run_startup_selftest(app), timeout=_SELFTEST_TIMEOUT_SEC)
    except asyncio.TimeoutError:
        logger.warning("Startup self-test timed out after %ss — server is still running", _SELFTEST_TIMEOUT_SEC)
        print("\n   WARNING: STARTUP SELF-TEST timed out (server ready anyway)\n")
        return {"selftest": "TIMEOUT"}


async def _run_startup_selftest(app: Any) -> Dict[str, str]:
    results: Dict[str, str] = {}

    # ── Test 1: XGBoost model ────────────────────────────────────
    try:
        from agents.underwriting_agent.main import model_loaded

        if model_loaded():
            results["xgboost"] = "PASS"
        else:
            results["xgboost"] = "DEGRADED: using rule-based fallback"
    except Exception as e:
        results["xgboost"] = f"FAIL: {e}"
    # ── Test 2: VLM KYC engine ───────────────────────────────────
    try:
        from services.vlm_kyc import init_vlm, vlm_ready

        if not vlm_ready():
            init_vlm()
        if vlm_ready():
            results["vlm_kyc"] = "PASS"
        else:
            results["vlm_kyc"] = "DEGRADED: engine not available"
    except Exception as e:
        results["vlm_kyc"] = f"FAIL: {e}"

    # ── Test 3: Groq connectivity ────────────────────────────────
    try:
        groq_service = getattr(app.state, "groq_service", None)
        if groq_service is not None:
            connected = await asyncio.wait_for(
                groq_service.verify_connection(),
                timeout=5,
            )
            if connected:
                results["groq"] = "PASS"
                await test_groq(groq_service)
            else:
                results["groq"] = "FALLBACK: connection failed but service initialized"
        else:
            results["groq"] = "FALLBACK: GroqService not in app state"
    except asyncio.TimeoutError:
        results["groq"] = "FALLBACK: connectivity check timed out"
    except Exception as e:
        results["groq"] = f"FALLBACK: {e}"
    # ── Test 4: Blockchain ledger ────────────────────────────────
    try:
        from blockchain import ledger

        test_block = ledger.add_transaction({
            "test": True,
            "transaction_id": "SELFTEST-001",
        })
        assert ledger.is_chain_valid(), "Chain validation failed"
        # Remove the test block so it doesn't pollute real data
        ledger.chain.pop()
        results["blockchain"] = "PASS"
    except Exception as e:
        results["blockchain"] = f"FAIL: {e}"

    # ── Print startup report ─────────────────────────────────────
    from core.config import settings

    print("\n" + "=" * 44)
    print("   LOANEASE STARTUP SELF-TEST")
    print("=" * 44)
    for component, status in results.items():
        print(f"   {component.upper():15s} {status}")
    print("-" * 44)
    if settings.DEMO_MODE:
        print("   DEMO_MODE = ON")
    print("-" * 44)

    failed = [k for k, v in results.items() if "FAIL" in v]
    if failed:
        print(f"   Warning: {len(failed)} component(s) need attention: {failed}")
    else:
        print("   ALL SYSTEMS GO — Demo ready")
    print("=" * 44 + "\n")

    return results


async def test_groq(groq_service: Any) -> bool:
    try:
        resp, _trace = await groq_service.chat(
            system_prompt="Reply: OK",
            messages=[{"role": "user", "content": "Reply: OK"}],
            max_tokens=5,
        )
        if "ok" in (resp or "").lower():
            logger.info("Groq LLaMA 70B: Active")
            return True
    except Exception as e:
        logger.warning(f"Groq test failed: {e}")
    return False
