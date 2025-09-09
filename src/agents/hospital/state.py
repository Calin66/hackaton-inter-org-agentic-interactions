from typing import Dict, Any
from uuid import uuid4
from threading import RLock
from copy import deepcopy

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
        with self._lock:
            # If caller provided a session id and it exists, reuse it
            if sid and sid in self._store:
                return sid
            # If caller provided a session id but it's new, create a session under that id
            if sid:
                self._store[sid] = {"status": "empty", "invoice": None}
                return sid
            # Otherwise generate a new session id
            return self.create()

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return deepcopy(self._store)

store = SessionStore()
