from __future__ import annotations
import json
from typing import Any, Dict, Optional
import requests

from .types import TaskCreateRequest

class HopeChainError(RuntimeError):
    pass

class HopeChainClient:
    """Lightweight Python SDK for HOPE Chain Gateway & Node RPC (v0.1.0)."""

    def __init__(self, base_url: str, api_key: Optional[str] = None, timeout_s: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s
        self._session = requests.Session()

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        if extra:
            h.update(extra)
        return h

    def create_task(self, req: TaskCreateRequest) -> Dict[str, Any]:
        r = self._session.post(f"{self.base_url}/tasks", headers=self._headers(), data=json.dumps(req), timeout=self.timeout_s)
        return self._handle(r)

    def get_task(self, task_id: str) -> Dict[str, Any]:
        r = self._session.get(f"{self.base_url}/tasks/{task_id}", headers=self._headers(), timeout=self.timeout_s)
        return self._handle(r)

    # Node RPC helpers
    def node_health(self) -> Dict[str, Any]:
        r = self._session.get(f"{self.base_url}/health", headers=self._headers(), timeout=self.timeout_s)
        return self._handle(r)

    def worker_execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        r = self._session.post(f"{self.base_url}/execute", headers=self._headers(), data=json.dumps(payload), timeout=self.timeout_s)
        return self._handle(r)

    def verifier_verify(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        r = self._session.post(f"{self.base_url}/verify", headers=self._headers(), data=json.dumps(payload), timeout=self.timeout_s)
        return self._handle(r)

    def _handle(self, r: requests.Response) -> Dict[str, Any]:
        ct = (r.headers.get("Content-Type") or "").lower()
        try:
            data = r.json() if "json" in ct else {"raw": r.text}
        except Exception:
            data = {"raw": r.text}
        if r.status_code >= 400:
            raise HopeChainError(f"HTTP {r.status_code}: {data}")
        if isinstance(data, dict) and data.get("ok") is False:
            raise HopeChainError(f"API error: {data}")
        return data
