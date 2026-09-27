"""
Thread-safe, versioned in-memory store for Vera Message Engine.
Handles idempotent context updates, stale version detection, and atomic replacement.
"""

import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

VALID_SCOPES = {"category", "merchant", "customer", "trigger"}


class ContextStore:
    def __init__(self):
        self._lock = threading.RLock()
        # key: (scope, context_id) -> {"version": int, "payload": dict, "stored_at": str, "delivered_at": str}
        self._store: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._init_time = datetime.now(timezone.utc)

    def push(
        self, scope: str, context_id: str, version: int, payload: Dict[str, Any], delivered_at: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any], int]:
        """
        Pushes a context entry.
        Returns: (accepted, response_data, http_status_code)
        """
        if not scope or scope not in VALID_SCOPES:
            return False, {
                "accepted": False,
                "reason": "invalid_scope",
                "details": f"Scope must be one of {sorted(list(VALID_SCOPES))}",
            }, 400

        if not context_id or not isinstance(context_id, str):
            return False, {
                "accepted": False,
                "reason": "invalid_context_id",
                "details": "context_id must be a non-empty string",
            }, 400

        if not isinstance(version, int) or version < 0:
            return False, {
                "accepted": False,
                "reason": "invalid_version",
                "details": "version must be a non-negative integer",
            }, 400

        if not isinstance(payload, dict):
            return False, {
                "accepted": False,
                "reason": "invalid_payload",
                "details": "payload must be a valid JSON object",
            }, 400

        now_iso = datetime.now(timezone.utc).isoformat()
        key = (scope, context_id)

        with self._lock:
            existing = self._store.get(key)
            if existing is not None:
                cur_ver = existing["version"]
                if version < cur_ver:
                    # Stale version - 409 Conflict
                    return False, {
                        "accepted": False,
                        "reason": "stale_version",
                        "current_version": cur_ver,
                        "attempted_version": version,
                    }, 409
                elif version == cur_ver:
                    # Idempotent re-post - 200 OK (no change)
                    return True, {
                        "accepted": True,
                        "ack_id": f"ack_{context_id}_v{version}",
                        "stored_at": existing["stored_at"],
                        "idempotent": True,
                    }, 200

            # New version or first insertion - replace atomically
            self._store[key] = {
                "version": version,
                "payload": payload,
                "stored_at": now_iso,
                "delivered_at": delivered_at or now_iso,
            }

            return True, {
                "accepted": True,
                "ack_id": f"ack_{context_id}_v{version}",
                "stored_at": now_iso,
            }, 200

    def get(self, scope: str, context_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            entry = self._store.get((scope, context_id))
            if entry:
                return entry["payload"]
            return None

    def get_entry(self, scope: str, context_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._store.get((scope, context_id))

    def get_all(self, scope: str) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {
                cid: entry["payload"]
                for (s, cid), entry in self._store.items()
                if s == scope
            }

    def counts(self) -> Dict[str, int]:
        with self._lock:
            c = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
            for (scope, _), _ in self._store.items():
                if scope in c:
                    c[scope] += 1
            return c

    def clear(self):
        with self._lock:
            self._store.clear()


# Global singleton instance
store = ContextStore()
