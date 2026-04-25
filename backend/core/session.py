from threading import Lock
from datetime import datetime, timedelta
from typing import Optional
import uuid

class SessionStore:
    def __init__(self):
        self._sessions = {}
        self._lock = Lock()
    
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
    
    def log_agent(self, session_id: str, agent_result: dict):
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id]["agent_log"].append(agent_result)
    
    def update_data(self, session_id: str, key: str, value):
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id]["data"][key] = value
    
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

# Single global instance
session_store = SessionStore()
