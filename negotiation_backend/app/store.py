from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Lock

from app.constants import SESSION_EXPIRY_HOURS


class SessionStore:
    def __init__(self) -> None:
        self._data: dict[str, dict] = {}
        self._lock = Lock()

    def create(self, session: dict) -> None:
        with self._lock:
            self._data[session["session_id"]] = session

    def get(self, session_id: str) -> dict | None:
        with self._lock:
            session = self._data.get(session_id)
            if session is None:
                return None
            return session

    def update(self, session_id: str, session: dict) -> None:
        with self._lock:
            self._data[session_id] = session

    def count_active(self) -> int:
        with self._lock:
            return sum(1 for s in self._data.values() if s.get("status") == "active")

    def mark_expired_if_needed(self, session: dict) -> bool:
        if session.get("status") not in {"active", "accepted"}:
            return False
        created_at = datetime.fromisoformat(session["created_at"])
        now = datetime.now(timezone.utc)
        if now - created_at > timedelta(hours=SESSION_EXPIRY_HOURS):
            session["status"] = "expired"
            return True
        return False
