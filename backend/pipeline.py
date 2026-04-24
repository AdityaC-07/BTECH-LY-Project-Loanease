from __future__ import annotations

import time
from copy import deepcopy
from typing import Any

from agents import (
    BlockchainAuditAgent,
    CreditUnderwritingAgent,
    KYCVerificationAgent,
    MasterOrchestratorAgent,
    NegotiationAgent,
)


class LoanPipeline:
    def __init__(self):
        self.kyc = KYCVerificationAgent()
        self.credit = CreditUnderwritingAgent()
        self.negotiation = NegotiationAgent()
        self.blockchain = BlockchainAuditAgent()
        self.master = MasterOrchestratorAgent(
            agents={
                "KYCVerificationAgent": self.kyc,
                "CreditUnderwritingAgent": self.credit,
                "Negotiation Agent": self.negotiation,
                "BlockchainAuditAgent": self.blockchain,
            }
        )
        self.agent_log: list[dict[str, Any]] = []

    async def run_stage(self, stage: str, payload: dict) -> dict:
        """
        Run one pipeline stage with full trace logging.

        Flow:
        1) Master inspects context and suggests action
        2) Stage agent executes
        3) Master inspects result and decides next stage
        4) All reasoning snapshots are appended to agent_log
        """
        session_id = payload.get("session_id", f"session_{int(time.time())}")
        language = payload.get("language", "en")

        master_pre = self._master_decide(
            session_id=session_id,
            user_message=payload.get("user_message", f"continue {stage}"),
            payload=payload,
            current_stage=stage,
        )
        self._log_step(
            stage=stage,
            actor="MasterOrchestratorAgent",
            status="SUCCESS",
            reasoning=master_pre.get("reasoning", ""),
            output=master_pre,
        )

        agent_name, agent_payload = self._resolve_stage_agent(stage, payload, session_id)
        agent_result = agent_name.run(agent_payload)
        self._log_step(
            stage=stage,
            actor=agent_result.agent_name,
            status=agent_result.status.value.upper(),
            reasoning=agent_result.reasoning,
            output=agent_result.output,
        )

        master_post = self._master_decide(
            session_id=session_id,
            user_message=f"{stage} completed",
            payload={**payload, "last_agent": agent_result.agent_name, "last_output": agent_result.output},
            current_stage=stage,
        )
        self._log_step(
            stage=stage,
            actor="MasterOrchestratorAgent",
            status="SUCCESS",
            reasoning=master_post.get("reasoning", ""),
            output=master_post,
        )

        return {
            "session_id": session_id,
            "stage": stage,
            "agent": agent_result.agent_name,
            "result": agent_result.output,
            "master_decision": master_post,
            "next_stage": self._derive_next_stage(stage, agent_result.output, master_post),
        }

    def get_agent_log(self) -> list:
        # Returns full trace of which agent did what and why — for demo transparency
        return self.agent_log

    def _resolve_stage_agent(self, stage: str, payload: dict, session_id: str):
        stage_key = (stage or "").strip().lower()
        if stage_key in {"kyc", "kyc_verification", "kyc_pending"}:
            return self.kyc, {
                "pan_number": payload.get("pan_number"),
                "aadhaar_number": payload.get("aadhaar_number"),
                "pan_image": payload.get("pan_image"),
                "aadhaar_image": payload.get("aadhaar_image"),
                "session_id": session_id,
            }
        if stage_key in {"credit", "underwriting", "credit_assessment"}:
            return self.credit, {
                "pan_number": payload.get("pan_number"),
                "applicant_income": payload.get("applicant_income", 50000),
                "loan_amount": payload.get("loan_amount", 500000),
                "loan_term": payload.get("loan_term", 60),
                "session_id": session_id,
            }
        if stage_key in {"negotiation", "offer", "offer_generated"}:
            return self.negotiation, {
                "loan_details": {
                    "loan_amount": payload.get("loan_amount", 500000),
                    "loan_term": payload.get("loan_term", 60),
                },
                "offered_rate": payload.get("offered_rate", 11.5),
                "risk_tier": payload.get("risk_tier", "Medium Risk"),
                "max_negotiation_rounds": payload.get("max_negotiation_rounds", 3),
                "negotiation_requested": payload.get("negotiation_requested", False),
                "counter_rate": payload.get("counter_rate"),
                "user_message": payload.get("user_message", ""),
                "current_rate": payload.get("current_rate", payload.get("offered_rate", 11.5)),
                "rounds_taken": payload.get("rounds_taken", 0),
                "session_id": session_id,
            }
        if stage_key in {"blockchain", "sanction", "accepted"}:
            return self.blockchain, {
                "applicant_name": payload.get("applicant_name", "Applicant"),
                "loan_amount": payload.get("loan_amount", 500000),
                "tenure_months": payload.get("tenure_months", payload.get("loan_term", 60)),
                "final_rate": payload.get("final_rate", payload.get("offered_rate", 11.5)),
                "emi": payload.get("emi", 0),
                "total_payable": payload.get("total_payable", 0),
                "total_interest": payload.get("total_interest", 0),
                "session_id": session_id,
            }
        raise ValueError(f"Unsupported stage '{stage}'. Use kyc, credit, negotiation, or blockchain.")

    def _derive_next_stage(self, current_stage: str, agent_output: dict, master_output: dict) -> str | None:
        explicit_stage = master_output.get("new_stage")
        if explicit_stage:
            return explicit_stage
        if isinstance(agent_output, dict) and agent_output.get("next_agent") == "BlockchainAuditAgent":
            return "ACCEPTED"
        progression = {
            "kyc": "KYC_VERIFIED",
            "credit": "OFFER_GENERATED",
            "negotiation": "ACCEPTED",
            "blockchain": "SANCTIONED",
        }
        return progression.get((current_stage or "").strip().lower())

    def _master_decide(self, session_id: str, user_message: str, payload: dict, current_stage: str) -> dict:
        context = {
            "stage": current_stage.upper(),
            "data": payload,
            "history": [],
            "session_id": session_id,
        }
        return self.master._fallback_decision(user_message, context)

    def _log_step(self, stage: str, actor: str, status: str, reasoning: str, output: dict) -> None:
        self.agent_log.append(
            {
                "timestamp": time.time(),
                "stage": stage,
                "actor": actor,
                "status": status,
                "reasoning": reasoning,
                "output": deepcopy(output) if isinstance(output, dict) else output,
            }
        )
