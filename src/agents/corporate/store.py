# agents/corporate/store.py
from threading import RLock
from typing import Dict
from .models import CorporateDecision


class DecisionStore:
    def __init__(self):
        self._d: Dict[str, CorporateDecision] = {}
        self._lock = RLock()

    def put(self, dec: CorporateDecision):
        with self._lock:
            self._d[dec.decision_id] = dec

    def get(self, decision_id: str) -> CorporateDecision | None:
        with self._lock:
            return self._d.get(decision_id)

    def all(self):
        with self._lock:
            return list(self._d.values())


store = DecisionStore()
