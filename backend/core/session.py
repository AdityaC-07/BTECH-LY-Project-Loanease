import json
import logging
from pathlib import Path
from threading import Lock
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import uuid


logger = logging.getLogger("loanease.session")
SESSION_FILE = Path("data/sessions.json")

class SessionStore:
    def __init__(self):
        self._sessions = {}
        self._global_logs = []
        self._MAX_GLOBAL_LOGS = 100
        self._lock = Lock()
        self._load_from_disk()

    def _load_from_disk(self):
        try:
            if SESSION_FILE.exists():
                with open(SESSION_FILE, "r", encoding="utf-8") as file:
                    self._sessions = json.load(file)
                logger.info("Loaded %s sessions from disk", len(self._sessions))
        except Exception as exc:
            logger.warning("Session load failed: %s", exc)
            self._sessions = {}

    def _save_to_disk(self):
        try:
            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(SESSION_FILE, "w", encoding="utf-8") as file:
                json.dump(self._sessions, file, default=str, indent=2)
        except Exception as exc:
            logger.warning("Session save failed: %s", exc)
    
    def create(self, initial_data: dict) -> str:
        session_id = str(uuid.uuid4())[:8].upper()
        with self._lock:
            self._sessions[session_id] = {
                "id": session_id,
                "created_at": datetime.utcnow().isoformat(),
                "expires_at": (datetime.utcnow() + timedelta(hours=24)).isoformat(),
                "stage": "INITIATED",
                "agent_log": [],
                "data": initial_data
            }
            self._save_to_disk()
        return session_id

    def get_or_create(self, session_id: str, initial_data: Optional[dict] = None) -> dict:
        """Get an existing session or create one with a provided session_id."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                return session

            payload = initial_data or {}
            self._sessions[session_id] = {
                "id": session_id,
                "created_at": datetime.utcnow().isoformat(),
                "expires_at": (datetime.utcnow() + timedelta(hours=24)).isoformat(),
                "stage": payload.get("stage", "INITIATED"),
                "agent_log": payload.get("agent_log", []),
                "data": payload.get("data", {}),
            }
            self._save_to_disk()
            return self._sessions[session_id]
    
    def get(self, session_id: str) -> Optional[dict]:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            # Check expiry
            expires = datetime.fromisoformat(session["expires_at"])
            if datetime.utcnow() > expires:
                del self._sessions[session_id]
                return None
            return session
    
    def update_stage(self, session_id: str, stage: str):
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id]["stage"] = stage
                self._save_to_disk()
    
    def log_agent(self, session_id: str, agent_result: dict):
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id]["agent_log"].append(agent_result)
                
                # Add to global logs
                global_entry = {
                    "session_id": session_id,
                    "timestamp": agent_result.get("timestamp", datetime.utcnow().isoformat()),
                    "agent": agent_result.get("agent", "Unknown"),
                    "action": agent_result.get("action", "Processed"),
                    "status": agent_result.get("status", "SUCCESS")
                }
                self._global_logs.insert(0, global_entry)
                if len(self._global_logs) > self._MAX_GLOBAL_LOGS:
                    self._global_logs.pop()
    
    def update_data(self, session_id: str, key: str, value):
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id]["data"][key] = value
                self._save_to_disk()
    
    def cleanup_expired(self):
        # Call periodically to free memory
        now = datetime.utcnow()
        with self._lock:
            expired = [
                k for k, v in self._sessions.items()
                if datetime.fromisoformat(v["expires_at"]) < now
            ]
            for k in expired:
                del self._sessions[k]
            if expired:
                self._save_to_disk()

    def clear_all(self) -> int:
        """Clear all sessions. Returns number of sessions cleared."""
        with self._lock:
            count = len(self._sessions)
            self._sessions.clear()
            self._global_logs.clear()
            self._save_to_disk()
        return count

    def get_global_activity(self, limit: int = 20) -> list:
        """Get the most recent system-wide agent activity"""
        with self._lock:
            return self._global_logs[:limit]

    def record_kyc_event(
        self,
        session_id: str,
        factor: str,
        event: str,
        result: str,
        details: Optional[dict] = None,
    ) -> None:
        """
        Record a KYC audit event.

        factor: "FA1", "FA2", "FA3"
        event: e.g. "PAN_EXTRACTED", "PASSED", "OTP_SENT"
        result: human-readable outcome
        """
        audit_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "factor": factor,
            "event": event,
            "result": result,
            "details": details or {},
        }

        with self._lock:
            if session_id in self._sessions:
                audit_log = self._sessions[session_id].setdefault("kyc_audit_trail", [])
                audit_log.append(audit_entry)
                self._save_to_disk()

    def get_kyc_audit_trail(self, session_id: str) -> Optional[list]:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            return list(session.get("kyc_audit_trail", []))

    def build_kyc_audit_summary(self, session_id: str, trail: list) -> dict[str, Any]:
        fa1_events = sum(1 for entry in trail if entry.get("factor") == "FA1")
        fa2_events = sum(1 for entry in trail if entry.get("factor") == "FA2")
        fa3_events = sum(1 for entry in trail if entry.get("factor") == "FA3")

        total_duration_seconds = 0
        if len(trail) >= 2:
            try:
                first = datetime.fromisoformat(trail[0]["timestamp"].replace("Z", "+00:00"))
                last = datetime.fromisoformat(trail[-1]["timestamp"].replace("Z", "+00:00"))
                total_duration_seconds = max(0, int((last - first).total_seconds()))
            except (KeyError, ValueError, TypeError):
                total_duration_seconds = 0

        final_status = "PENDING"
        for entry in reversed(trail):
            event = entry.get("event", "")
            factor = entry.get("factor", "")
            result = str(entry.get("result", "")).lower()
            if factor == "FA3" and event == "OTP_VERIFIED" and result == "success":
                final_status = "VERIFIED"
                break
            if event in {"FAILED", "OTP_FAILED"} or result == "failed":
                final_status = "FAILED"
                break

        with self._lock:
            session = self._sessions.get(session_id) or {}
            stage = session.get("stage", "")
            if final_status == "PENDING" and stage == "KYC_VERIFIED":
                final_status = "VERIFIED"

        return {
            "fa1_events": fa1_events,
            "fa2_events": fa2_events,
            "fa3_events": fa3_events,
            "total_duration_seconds": total_duration_seconds,
            "final_status": final_status,
        }


# Single global instance
session_store = SessionStore()
