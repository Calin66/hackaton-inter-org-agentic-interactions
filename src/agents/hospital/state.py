from typing import Dict, Any
from uuid import uuid4
from threading import RLock

class SessionStore:
    def __init__(self):
        self._lock = RLock()
        self._store: Dict[str, Dict[str, Any]] = {}

    def create(self) -> str:
        sid = str(uuid4())
        with self._lock:
            self._store[sid] = {"status": "empty", "invoice": None}
        return sid

    def get(self, sid: str):
        with self._lock:
            return self._store.get(sid)

    def upsert(self, sid: str, data: Dict[str, Any]):
        with self._lock:
            self._store[sid] = data

    def ensure(self, sid: str) -> str:
        if sid and self.get(sid) is not None:
            return sid
        return self.create()

store = SessionStore()
