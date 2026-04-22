from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
import sqlite3
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from fastapi.responses import HTMLResponse


class SimpleChainDB:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chain_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor_did TEXT,
                    actor_name TEXT,
                    actor_type TEXT,
                    impact_score REAL NOT NULL DEFAULT 0.0,
                    trust_delta REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL,
                    record_hash TEXT NOT NULL,
                    prev_hash TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def _last_hash(self) -> str | None:
        conn = self._connect()
        try:
            row = conn.execute('SELECT record_hash FROM chain_events ORDER BY id DESC LIMIT 1').fetchone()
            return row['record_hash'] if row else None
        finally:
            conn.close()

    def add_event(self, *, trace_id: str, event_type: str, actor_name: str, actor_type: str, impact_score: float, trust_delta: float, payload: dict[str, Any], actor_did: str | None = None) -> dict[str, Any]:
        prev_hash = self._last_hash()
        created_at = utc_now()
        actor_did = actor_did or f'did:hope:{re.sub(r"[^a-zA-Z0-9]+", "-", actor_name.lower()).strip("-") or "unknown"}'
        canonical = json.dumps({
            'trace_id': trace_id, 'event_type': event_type, 'actor_did': actor_did, 'actor_name': actor_name,
            'actor_type': actor_type, 'impact_score': impact_score, 'trust_delta': trust_delta,
            'payload': payload, 'prev_hash': prev_hash, 'created_at': created_at
        }, sort_keys=True)
        import hashlib
        record_hash = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
        conn = self._connect()
        try:
            conn.execute(
                'INSERT INTO chain_events (trace_id,event_type,actor_did,actor_name,actor_type,impact_score,trust_delta,payload_json,record_hash,prev_hash,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                (trace_id, event_type, actor_did, actor_name, actor_type, float(impact_score), float(trust_delta), json.dumps(payload), record_hash, prev_hash, created_at)
            )
            conn.commit()
        finally:
            conn.close()
        return {
            'trace_id': trace_id, 'event_type': event_type, 'actor_did': actor_did, 'actor_name': actor_name,
            'actor_type': actor_type, 'impact_score': round(float(impact_score), 4), 'trust_delta': round(float(trust_delta), 4),
            'payload': payload, 'record_hash': record_hash, 'prev_hash': prev_hash, 'created_at': created_at
        }

    def list_recent_events(self, limit: int = 20) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute('SELECT * FROM chain_events ORDER BY id DESC LIMIT ?', (max(1, min(limit, 200)),)).fetchall()
            items = []
            for row in rows:
                item = dict(row)
                item['payload'] = json.loads(item.pop('payload_json') or '{}')
                items.append(item)
            return items
        finally:
            conn.close()

    def verify_chain(self) -> dict[str, Any]:
        conn = self._connect()
        try:
            rows = conn.execute('SELECT * FROM chain_events ORDER BY id ASC').fetchall()
            import hashlib
            prev_hash = None
            checked = 0
            for row in rows:
                payload = json.loads(row['payload_json'] or '{}')
                canonical = json.dumps({
                    'trace_id': row['trace_id'], 'event_type': row['event_type'], 'actor_did': row['actor_did'], 'actor_name': row['actor_name'],
                    'actor_type': row['actor_type'], 'impact_score': row['impact_score'], 'trust_delta': row['trust_delta'],
                    'payload': payload, 'prev_hash': row['prev_hash'], 'created_at': row['created_at']
                }, sort_keys=True)
                expected = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
                if row['prev_hash'] != prev_hash:
                    return {'ok': False, 'checked_records': checked, 'error': f'Prev hash mismatch at id {row["id"]}'}
                if row['record_hash'] != expected:
                    return {'ok': False, 'checked_records': checked, 'error': f'Record hash mismatch at id {row["id"]}'}
                prev_hash = row['record_hash']
                checked += 1
            return {'ok': True, 'checked_records': checked}
        finally:
            conn.close()


class HOPEChain:
    def __init__(self, db_path: str = 'hopechain_did.db') -> None:
        self.db = SimpleChainDB(db_path)

    def record_node_execution(self, *, trace_id: str, actor_name: str, output_preview: str, confidence: float, duration_ms: int, success: bool) -> dict[str, Any]:
        trust_delta = 0.03 if success else -0.05
        return self.db.add_event(
            trace_id=trace_id,
            event_type='node_execution',
            actor_name=actor_name,
            actor_type='ai_node',
            impact_score=confidence,
            trust_delta=trust_delta,
            payload={'output_preview': summarize_prompt(output_preview, 220), 'confidence': confidence, 'duration_ms': duration_ms, 'success': success},
        )

    def record_goal_decision(self, *, trace_id: str, actor_name: str, goal_id: str, rank: int, expected_impact: float, vicdan_alignment: str) -> dict[str, Any]:
        trust_delta = 0.04 if vicdan_alignment == 'ACCEPT' else (0.01 if vicdan_alignment in {'MODIFY', 'REVIEW'} else -0.04)
        return self.db.add_event(
            trace_id=trace_id,
            event_type='goal_decision',
            actor_name=actor_name,
            actor_type='governance',
            impact_score=expected_impact,
            trust_delta=trust_delta,
            payload={'goal_id': goal_id, 'rank': rank, 'expected_impact': expected_impact, 'vicdan_alignment': vicdan_alignment},
        )


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    app_name: str = os.getenv("APP_NAME", "HOPEverse — crafted by Erhan")
    app_env: str = os.getenv("APP_ENV", "dev")
    app_version: str = os.getenv("APP_VERSION", "v1")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    db_path: str = os.getenv("HOPETENSOR_DB_PATH", "hopetensor_v1.db")

    enable_local_node: bool = env_bool("ENABLE_LOCAL_NODE", True)
    enable_external_node: bool = env_bool("ENABLE_EXTERNAL_NODE", True)
    enable_retrieval_node: bool = env_bool("ENABLE_RETRIEVAL_NODE", False)

    default_policy_profile: str = os.getenv("DEFAULT_POLICY_PROFILE", "default")
    node_timeout_ms: int = int(os.getenv("NODE_TIMEOUT_MS", "20000"))
    strict_mode_min_nodes: int = int(os.getenv("STRICT_MODE_MIN_NODES", "2"))

    external_llm_base_url: str = os.getenv("EXTERNAL_LLM_BASE_URL", "https://api.openai.com/v1")
    external_llm_api_key: Optional[str] = os.getenv("EXTERNAL_LLM_API_KEY")
    external_llm_model: str = os.getenv("EXTERNAL_LLM_MODEL", "gpt-4o-mini")

    local_node_name: str = os.getenv("LOCAL_NODE_NAME", "local-1")
    external_node_name: str = os.getenv("EXTERNAL_NODE_NAME", "external-1")
    retrieval_node_name: str = os.getenv("RETRIEVAL_NODE_NAME", "retrieval-1")


SETTINGS = Settings()

logging.basicConfig(
    level=getattr(logging, SETTINGS.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("hopeverse")
HOPECHAIN = HOPEChain("hopechain_did.db")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    return set(words)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def summarize_prompt(prompt: str, max_len: int = 180) -> str:
    text = normalize_whitespace(prompt)
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


class ReasonRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    context: Optional[dict[str, Any]] = None
    policy_profile: Optional[str] = None
    required_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    mode: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class ReasonResponse(BaseModel):
    answer: str
    confidence: float
    selected_nodes: list[str]
    verification_summary: str
    vicdan_status: str
    trace_id: str


class TraceResponse(BaseModel):
    trace_id: str
    task_id: str
    selected_nodes: list[str]
    verification_summary: str
    vicdan_status: str
    final_output: str
    total_duration_ms: int
    created_at: str
    candidates: list[dict[str, Any]]


class NodeStatusResponse(BaseModel):
    node_id: str
    node_type: str
    capabilities: list[str]
    enabled: bool
    trust_score: float
    reputation_score: float


class TaskContext(BaseModel):
    task_id: str
    trace_id: str
    requester_id: Optional[str] = None
    task_type: str
    policy_profile: str
    required_confidence: Optional[float] = None
    prompt: str
    context_payload: Optional[dict[str, Any]] = None
    metadata: Optional[dict[str, Any]] = None
    created_at: str


class CandidateAnswer(BaseModel):
    candidate_id: str
    task_id: str
    node_id: str
    output: Optional[str] = None
    confidence_self_reported: Optional[float] = None
    evidence_refs: list[str] = Field(default_factory=list)
    duration_ms: int = 0
    error: Optional[str] = None


class VerificationResult(BaseModel):
    task_id: str
    agreement_score: float
    evidence_score: float
    contradiction_flags: list[str]
    confidence_score: float
    candidate_rankings: list[str]
    selected_candidate_id: Optional[str] = None
    verification_summary: str


class VicdanResult(BaseModel):
    task_id: str
    decision: str
    risk_scores: dict[str, float]
    rationale: str
    required_modification: Optional[str] = None


class FinalResponse(BaseModel):
    answer: str
    confidence: float
    selected_nodes: list[str]
    verification_summary: str
    vicdan_status: str
    trace_id: str


class Database:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    node_id TEXT UNIQUE NOT NULL,
                    node_type TEXT NOT NULL,
                    capabilities_json TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    trust_score REAL NOT NULL,
                    reputation_score REAL NOT NULL,
                    cost_weight REAL NOT NULL,
                    latency_weight REAL NOT NULL,
                    policy_tags_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT UNIQUE NOT NULL,
                    trace_id TEXT NOT NULL,
                    requester_id TEXT,
                    task_type TEXT NOT NULL,
                    policy_profile TEXT NOT NULL,
                    required_confidence REAL,
                    prompt TEXT NOT NULL,
                    context_json TEXT,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS candidate_answers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id TEXT UNIQUE NOT NULL,
                    task_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    output_text TEXT,
                    confidence_self_reported REAL,
                    evidence_refs_json TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    error_text TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS verification_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT UNIQUE NOT NULL,
                    agreement_score REAL NOT NULL,
                    evidence_score REAL NOT NULL,
                    contradiction_flags_json TEXT NOT NULL,
                    confidence_score REAL NOT NULL,
                    candidate_rankings_json TEXT NOT NULL,
                    selected_candidate_id TEXT,
                    verification_summary TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS vicdan_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT UNIQUE NOT NULL,
                    decision TEXT NOT NULL,
                    risk_scores_json TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    required_modification TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS traces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT UNIQUE NOT NULL,
                    task_id TEXT UNIQUE NOT NULL,
                    request_summary TEXT NOT NULL,
                    selected_nodes_json TEXT NOT NULL,
                    candidate_ids_json TEXT NOT NULL,
                    verification_summary TEXT NOT NULL,
                    vicdan_status TEXT NOT NULL,
                    final_output TEXT NOT NULL,
                    total_duration_ms INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    def upsert_node(self, node: "BaseNode") -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO nodes (
                    node_id, node_type, capabilities_json, enabled,
                    trust_score, reputation_score, cost_weight,
                    latency_weight, policy_tags_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    node_type=excluded.node_type,
                    capabilities_json=excluded.capabilities_json,
                    enabled=excluded.enabled,
                    trust_score=excluded.trust_score,
                    reputation_score=excluded.reputation_score,
                    cost_weight=excluded.cost_weight,
                    latency_weight=excluded.latency_weight,
                    policy_tags_json=excluded.policy_tags_json
                """,
                (
                    node.node_id,
                    node.node_type,
                    json.dumps(node.capabilities),
                    1 if node.enabled else 0,
                    node.trust_score,
                    node.reputation_score,
                    node.cost_weight,
                    node.latency_weight,
                    json.dumps(node.policy_tags),
                    utc_now(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def save_task(self, task: TaskContext) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO tasks (
                    task_id, trace_id, requester_id, task_type, policy_profile,
                    required_confidence, prompt, context_json, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.task_id,
                    task.trace_id,
                    task.requester_id,
                    task.task_type,
                    task.policy_profile,
                    task.required_confidence,
                    task.prompt,
                    json.dumps(task.context_payload or {}),
                    json.dumps(task.metadata or {}),
                    task.created_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def save_candidates(self, candidates: list["CandidateAnswer"]) -> None:
        conn = self._connect()
        try:
            for c in candidates:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO candidate_answers (
                        candidate_id, task_id, node_id, output_text,
                        confidence_self_reported, evidence_refs_json,
                        duration_ms, error_text, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        c.candidate_id,
                        c.task_id,
                        c.node_id,
                        c.output,
                        c.confidence_self_reported,
                        json.dumps(c.evidence_refs),
                        c.duration_ms,
                        c.error,
                        utc_now(),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def save_verification(self, vr: "VerificationResult") -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO verification_results (
                    task_id, agreement_score, evidence_score,
                    contradiction_flags_json, confidence_score,
                    candidate_rankings_json, selected_candidate_id,
                    verification_summary, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    vr.task_id,
                    vr.agreement_score,
                    vr.evidence_score,
                    json.dumps(vr.contradiction_flags),
                    vr.confidence_score,
                    json.dumps(vr.candidate_rankings),
                    vr.selected_candidate_id,
                    vr.verification_summary,
                    utc_now(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def save_vicdan(self, vc: "VicdanResult") -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO vicdan_results (
                    task_id, decision, risk_scores_json, rationale,
                    required_modification, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    vc.task_id,
                    vc.decision,
                    json.dumps(vc.risk_scores),
                    vc.rationale,
                    vc.required_modification,
                    utc_now(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def save_trace(
        self,
        trace_id: str,
        task_id: str,
        request_summary: str,
        selected_nodes: list[str],
        candidate_ids: list[str],
        verification_summary: str,
        vicdan_status: str,
        final_output: str,
        total_duration_ms: int,
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO traces (
                    trace_id, task_id, request_summary, selected_nodes_json,
                    candidate_ids_json, verification_summary, vicdan_status,
                    final_output, total_duration_ms, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace_id,
                    task_id,
                    request_summary,
                    json.dumps(selected_nodes),
                    json.dumps(candidate_ids),
                    verification_summary,
                    vicdan_status,
                    final_output,
                    total_duration_ms,
                    utc_now(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_trace(self, trace_id: str) -> Optional[dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM traces WHERE trace_id = ?", (trace_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_candidates_by_task(self, task_id: str) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT candidate_id, task_id, node_id, output_text,
                       confidence_self_reported, evidence_refs_json,
                       duration_ms, error_text, created_at
                FROM candidate_answers
                WHERE task_id = ?
                ORDER BY id ASC
                """,
                (task_id,),
            ).fetchall()

            results: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                item["evidence_refs"] = json.loads(item["evidence_refs_json"] or "[]")
                item.pop("evidence_refs_json", None)
                item["output"] = item.pop("output_text", None)
                item["error"] = item.pop("error_text", None)
                results.append(item)
            return results
        finally:
            conn.close()


DB = Database(SETTINGS.db_path)


class TaskClassifier:
    @staticmethod
    def classify(prompt: str, metadata: Optional[dict[str, Any]] = None) -> str:
        text = prompt.lower()
        if any(k in text for k in ["calculate", "equation", "solve", "math"]):
            return "math"
        if any(k in text for k in ["api", "python", "bug", "code", "fastapi", "docker"]):
            return "technical"
        if any(k in text for k in ["drug", "weapon", "hack", "attack", "bypass"]):
            return "safety_sensitive"
        if any(k in text for k in ["source", "citation", "evidence", "verify"]):
            return "retrieval_recommended"
        return "general"


class BaseNode(ABC):
    node_id: str
    node_type: str
    capabilities: list[str]
    trust_score: float
    reputation_score: float
    cost_weight: float
    latency_weight: float
    policy_tags: list[str]
    enabled: bool

    @abstractmethod
    async def run(self, task: TaskContext) -> CandidateAnswer:
        raise NotImplementedError


class LocalNode(BaseNode):
    def __init__(self) -> None:
        self.node_id = SETTINGS.local_node_name
        self.node_type = "local"
        self.capabilities = ["general", "technical", "fallback"]
        self.trust_score = 0.70
        self.reputation_score = 0.70
        self.cost_weight = 0.10
        self.latency_weight = 0.35
        self.policy_tags = ["default", "strict", "safe"]
        self.enabled = SETTINGS.enable_local_node

    async def run(self, task: TaskContext) -> CandidateAnswer:
        start = time.perf_counter()
        try:
            prompt = normalize_whitespace(task.prompt)
            short = summarize_prompt(prompt, 500)
            if task.task_type == "technical":
                output = (
                    "Local node analysis: this looks like a technical request. "
                    "Recommended path is structured reasoning, explicit assumptions, "
                    "and verification before release. Prompt summary: " + short
                )
            elif task.task_type == "math":
                output = (
                    "Local node analysis: this appears to be a math-oriented request. "
                    "Use deterministic validation in addition to language reasoning. "
                    "Prompt summary: " + short
                )
            elif task.task_type == "safety_sensitive":
                output = (
                    "Local node analysis: this request may be safety-sensitive and requires strict Vicdan review. "
                    "Prompt summary: " + short
                )
            else:
                output = (
                    "Local node analysis: this request can be handled through federated reasoning with "
                    "verification and policy checks. Prompt summary: " + short
                )

            return CandidateAnswer(
                candidate_id=generate_id("cand"),
                task_id=task.task_id,
                node_id=self.node_id,
                output=output,
                confidence_self_reported=0.62,
                evidence_refs=[],
                duration_ms=int((time.perf_counter() - start) * 1000),
                error=None,
            )
        except Exception as exc:
            return CandidateAnswer(
                candidate_id=generate_id("cand"),
                task_id=task.task_id,
                node_id=self.node_id,
                output=None,
                confidence_self_reported=None,
                evidence_refs=[],
                duration_ms=int((time.perf_counter() - start) * 1000),
                error=f"local_node_error: {exc}",
            )


class ExternalLLMNode(BaseNode):
    def __init__(self) -> None:
        self.node_id = SETTINGS.external_node_name
        self.node_type = "external_llm"
        self.capabilities = ["general", "technical", "higher_reasoning"]
        self.trust_score = 0.82
        self.reputation_score = 0.78
        self.cost_weight = 0.75
        self.latency_weight = 0.60
        self.policy_tags = ["default", "strict"]
        self.enabled = True

    async def run(self, task: TaskContext) -> CandidateAnswer:
        start = time.perf_counter()

        if SETTINGS.external_llm_api_key:
            headers = {
                "Authorization": f"Bearer {SETTINGS.external_llm_api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": SETTINGS.external_llm_model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a reasoning node inside the HOPEverse intelligence engine, HOPEtensor. "
                            "Produce a concise, careful answer. State assumptions when needed."
                        ),
                    },
                    {"role": "user", "content": task.prompt},
                ],
                "temperature": 0.2,
            }

            try:
                timeout = SETTINGS.node_timeout_ms / 1000
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        f"{SETTINGS.external_llm_base_url.rstrip('/')}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                    response.raise_for_status()
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]

                return CandidateAnswer(
                    candidate_id=generate_id("cand"),
                    task_id=task.task_id,
                    node_id=self.node_id,
                    output=normalize_whitespace(content),
                    confidence_self_reported=0.78,
                    evidence_refs=[],
                    duration_ms=int((time.perf_counter() - start) * 1000),
                    error=None,
                )
            except Exception as exc:
                return CandidateAnswer(
                    candidate_id=generate_id("cand"),
                    task_id=task.task_id,
                    node_id=self.node_id,
                    output=None,
                    confidence_self_reported=None,
                    evidence_refs=[],
                    duration_ms=int((time.perf_counter() - start) * 1000),
                    error=f"external_node_error: {exc}",
                )

        try:
            prompt = normalize_whitespace(task.prompt).lower()
            if "hallucination" in prompt:
                output = (
                    "External node analysis: single-model systems hallucinate because generation is probabilistic, "
                    "grounding is incomplete, and confidence is often implicit rather than explicit. "
                    "Governed multi-node execution reduces risk by comparing reasoning paths, scoring agreement, "
                    "and applying final policy control before release."
                )
            elif task.task_type == "technical":
                output = (
                    "External node analysis: this technical request benefits from a second reasoning path. "
                    "A robust production pattern is independent node execution, verification scoring, "
                    "and release only after consistency checks."
                )
            else:
                output = (
                    "External node analysis: this request benefits from structured multi-node reasoning. "
                    "Independent candidate generation improves trust when combined with verification and policy review."
                )

            return CandidateAnswer(
                candidate_id=generate_id("cand"),
                task_id=task.task_id,
                node_id=self.node_id,
                output=output,
                confidence_self_reported=0.78,
                evidence_refs=["synthetic_reasoning"],
                duration_ms=int((time.perf_counter() - start) * 1000),
                error=None,
            )
        except Exception as exc:
            return CandidateAnswer(
                candidate_id=generate_id("cand"),
                task_id=task.task_id,
                node_id=self.node_id,
                output=None,
                confidence_self_reported=None,
                evidence_refs=[],
                duration_ms=int((time.perf_counter() - start) * 1000),
                error=f"external_node_error: {exc}",
            )


class RetrievalNode(BaseNode):
    def __init__(self) -> None:
        self.node_id = SETTINGS.retrieval_node_name
        self.node_type = "retrieval"
        self.capabilities = ["retrieval", "evidence"]
        self.trust_score = 0.76
        self.reputation_score = 0.74
        self.cost_weight = 0.30
        self.latency_weight = 0.45
        self.policy_tags = ["default", "strict"]
        self.enabled = SETTINGS.enable_retrieval_node

    async def run(self, task: TaskContext) -> CandidateAnswer:
        start = time.perf_counter()
        try:
            output = (
                "Retrieval node placeholder: retrieval layer is available for future evidence-backed expansion. "
                "Current v1 single-file build returns a retrieval recommendation summary only."
            )
            return CandidateAnswer(
                candidate_id=generate_id("cand"),
                task_id=task.task_id,
                node_id=self.node_id,
                output=output,
                confidence_self_reported=0.55,
                evidence_refs=["retrieval_placeholder"],
                duration_ms=int((time.perf_counter() - start) * 1000),
                error=None,
            )
        except Exception as exc:
            return CandidateAnswer(
                candidate_id=generate_id("cand"),
                task_id=task.task_id,
                node_id=self.node_id,
                output=None,
                confidence_self_reported=None,
                evidence_refs=[],
                duration_ms=int((time.perf_counter() - start) * 1000),
                error=f"retrieval_node_error: {exc}",
            )


class NodeRegistry:
    def __init__(self) -> None:
        self._nodes: dict[str, BaseNode] = {}

    def register(self, node: BaseNode) -> None:
        self._nodes[node.node_id] = node
        DB.upsert_node(node)

    def get(self, node_id: str) -> Optional[BaseNode]:
        return self._nodes.get(node_id)

    def list_enabled(self) -> list[BaseNode]:
        return [node for node in self._nodes.values() if node.enabled]

    def select_for_task(self, task_type: str, policy_profile: str, mode: Optional[str] = None) -> list[BaseNode]:
        return self.list_enabled()


NODE_REGISTRY = NodeRegistry()
if SETTINGS.enable_local_node:
    NODE_REGISTRY.register(LocalNode())
NODE_REGISTRY.register(ExternalLLMNode())
if SETTINGS.enable_retrieval_node:
    NODE_REGISTRY.register(RetrievalNode())


class VerificationEngine:
    @staticmethod
    def compute_agreement_score(candidates: list[CandidateAnswer]) -> float:
        valid = [c for c in candidates if c.output and not c.error]
        if not valid:
            return 0.0
        if len(valid) == 1:
            return 0.55

        scores: list[float] = []
        for i in range(len(valid)):
            for j in range(i + 1, len(valid)):
                a = tokenize(valid[i].output or "")
                b = tokenize(valid[j].output or "")
                if not a or not b:
                    scores.append(0.0)
                    continue
                intersection = len(a & b)
                union = max(1, len(a | b))
                scores.append(intersection / union)
        return clamp(sum(scores) / len(scores)) if scores else 0.0

    @staticmethod
    def detect_contradictions(candidates: list[CandidateAnswer]) -> list[str]:
        valid = [c for c in candidates if c.output and not c.error]
        if len(valid) < 2:
            return []
        flags: list[str] = []
        texts = [c.output.lower() for c in valid if c.output]
        contradiction_markers = [("must", "must not"), ("is", "is not"), ("can", "cannot"), ("allowed", "not allowed")]
        joined = " || ".join(texts)
        for pos, neg in contradiction_markers:
            if pos in joined and neg in joined:
                flags.append(f"Potential contradiction between '{pos}' and '{neg}'")
        return flags

    @staticmethod
    def compute_evidence_score(candidates: list[CandidateAnswer]) -> float:
        valid = [c for c in candidates if not c.error]
        if not valid:
            return 0.0
        evidence_hits = sum(1 for c in valid if c.evidence_refs)
        convergence_bonus = 0.15 if len(valid) > 1 else 0.0
        return clamp((evidence_hits / len(valid)) * 0.75 + convergence_bonus)

    @staticmethod
    def compute_structural_validity(candidate: CandidateAnswer) -> float:
        if candidate.error or not candidate.output:
            return 0.0
        text = normalize_whitespace(candidate.output)
        if len(text) < 20:
            return 0.35
        if len(text) < 60:
            return 0.65
        return 0.90

    @staticmethod
    def candidate_weight(candidate: CandidateAnswer) -> float:
        node = NODE_REGISTRY.get(candidate.node_id)
        if not node:
            return 0.5
        return clamp((node.trust_score + node.reputation_score) / 2)

    @classmethod
    def calculate_confidence(cls, agreement_score: float, evidence_score: float, reputation_weight: float, structural_validity: float) -> float:
        raw = agreement_score * 0.35 + evidence_score * 0.20 + reputation_weight * 0.20 + structural_validity * 0.25
        return clamp(raw)

    @classmethod
    def verify(cls, task: TaskContext, candidates: list[CandidateAnswer]) -> VerificationResult:
        valid = [c for c in candidates if c.output and not c.error]
        if not valid:
            return VerificationResult(
                task_id=task.task_id,
                agreement_score=0.0,
                evidence_score=0.0,
                contradiction_flags=["No valid candidate outputs available"],
                confidence_score=0.0,
                candidate_rankings=[],
                selected_candidate_id=None,
                verification_summary="Verification failed: no valid candidate outputs.",
            )

        agreement_score = cls.compute_agreement_score(valid)
        evidence_score = cls.compute_evidence_score(valid)
        contradiction_flags = cls.detect_contradictions(valid)

        scored: list[tuple[CandidateAnswer, float]] = []
        for candidate in valid:
            structural_validity = cls.compute_structural_validity(candidate)
            reputation_weight = cls.candidate_weight(candidate)
            confidence = cls.calculate_confidence(agreement_score, evidence_score, reputation_weight, structural_validity)
            scored.append((candidate, confidence))

        scored.sort(key=lambda item: item[1], reverse=True)
        best_candidate, best_confidence = scored[0]
        rankings = [candidate.candidate_id for candidate, _ in scored]

        summary = (
            f"Agreement score {agreement_score:.2f}, evidence score {evidence_score:.2f}, "
            f"{len(contradiction_flags)} contradiction flags, selected node {best_candidate.node_id}."
        )

        return VerificationResult(
            task_id=task.task_id,
            agreement_score=agreement_score,
            evidence_score=evidence_score,
            contradiction_flags=contradiction_flags,
            confidence_score=best_confidence,
            candidate_rankings=rankings,
            selected_candidate_id=best_candidate.candidate_id,
            verification_summary=summary,
        )


class VicdanEngine:
    HARD_BLOCK_PATTERNS = [
        r"\bbuild a bomb\b",
        r"\bmake a bomb\b",
        r"\bhow to kill\b",
        r"\bcredit card fraud\b",
        r"\bsteal passwords\b",
        r"\bdeploy malware\b",
        r"\bransomware\b",
    ]

    RISK_KEYWORDS = {
        "harm_risk": ["kill", "weapon", "bomb", "poison", "attack"],
        "manipulation_risk": ["manipulate", "deceive", "coerce", "blackmail"],
        "privacy_risk": ["password", "secret", "private key", "stolen data"],
        "unsafe_execution_risk": ["bypass", "exploit", "hack", "malware"],
    }

    @classmethod
    def check_hard_rules(cls, text: str) -> Optional[str]:
        lower = text.lower()
        for pattern in cls.HARD_BLOCK_PATTERNS:
            if re.search(pattern, lower):
                return f"Hard-rule violation matched pattern: {pattern}"
        return None

    @classmethod
    def score_risks(cls, text: str) -> dict[str, float]:
        lower = text.lower()
        scores: dict[str, float] = {}
        for risk_name, keywords in cls.RISK_KEYWORDS.items():
            hits = sum(1 for keyword in keywords if keyword in lower)
            scores[risk_name] = clamp(hits / max(1, len(keywords)))
        return scores

    @staticmethod
    def context_modifier(task: TaskContext) -> float:
        if task.task_type == "safety_sensitive":
            return 0.25
        if task.policy_profile == "strict":
            return 0.20
        if task.policy_profile == "safe":
            return 0.15
        return 0.0

    @classmethod
    def evaluate(cls, task: TaskContext, selected_output: str) -> VicdanResult:
        hard_violation = cls.check_hard_rules(selected_output)
        risk_scores = cls.score_risks(selected_output)
        context_boost = cls.context_modifier(task)
        max_risk = clamp(max(risk_scores.values(), default=0.0) + context_boost)

        if hard_violation:
            return VicdanResult(task_id=task.task_id, decision="REJECT", risk_scores=risk_scores, rationale=hard_violation, required_modification="Replace with safe refusal.")
        if max_risk >= 0.80:
            return VicdanResult(task_id=task.task_id, decision="REJECT", risk_scores=risk_scores, rationale="Risk score exceeded reject threshold.", required_modification="Replace with safe refusal.")
        if max_risk >= 0.55:
            return VicdanResult(task_id=task.task_id, decision="REVIEW", risk_scores=risk_scores, rationale="Risk score exceeded review threshold.", required_modification="Return guarded answer with reduced operational detail.")
        if max_risk >= 0.35:
            return VicdanResult(task_id=task.task_id, decision="MODIFY", risk_scores=risk_scores, rationale="Moderate risk detected; output should be softened or constrained.", required_modification="Return moderated answer.")
        return VicdanResult(task_id=task.task_id, decision="ACCEPT", risk_scores=risk_scores, rationale="No blocking or elevated risk detected.", required_modification=None)

    @staticmethod
    def apply_decision(vicdan: VicdanResult, selected_output: str) -> str:
        if vicdan.decision == "ACCEPT":
            return selected_output
        if vicdan.decision == "MODIFY":
            return "Modified by Vicdan: the original answer was reduced to keep it high-level, non-operational, and safer.\n\n" + selected_output
        if vicdan.decision == "REVIEW":
            return "Vicdan review state: the request touches elevated-risk territory. Only a guarded, high-level response is returned.\n\n" + selected_output
        return "Vicdan rejection: the system cannot provide the requested output because it violates the active safety policy."


class Observer:
    @staticmethod
    def persist(task: TaskContext, candidates: list[CandidateAnswer], verification: VerificationResult, vicdan: VicdanResult, final_output: str, total_duration_ms: int) -> None:
        DB.save_task(task)
        DB.save_candidates(candidates)
        DB.save_verification(verification)
        DB.save_vicdan(vicdan)
        DB.save_trace(
            trace_id=task.trace_id,
            task_id=task.task_id,
            request_summary=summarize_prompt(task.prompt),
            selected_nodes=list({c.node_id for c in candidates}),
            candidate_ids=[c.candidate_id for c in candidates],
            verification_summary=verification.verification_summary,
            vicdan_status=vicdan.decision,
            final_output=final_output,
            total_duration_ms=total_duration_ms,
        )


class Orchestrator:
    def __init__(self, registry: NodeRegistry) -> None:
        self.registry = registry

    async def execute_reasoning(self, request: ReasonRequest) -> FinalResponse:
        started = time.perf_counter()
        trace_id = generate_id("trace")
        task_id = generate_id("task")

        task_type = TaskClassifier.classify(request.prompt, request.metadata)
        policy_profile = request.policy_profile or SETTINGS.default_policy_profile

        task = TaskContext(
            task_id=task_id,
            trace_id=trace_id,
            requester_id=None,
            task_type=task_type,
            policy_profile=policy_profile,
            required_confidence=request.required_confidence,
            prompt=request.prompt,
            context_payload=request.context,
            metadata=request.metadata,
            created_at=utc_now(),
        )

        selected_nodes = self.registry.select_for_task(task_type, policy_profile, request.mode)
        if not selected_nodes:
            raise HTTPException(status_code=503, detail="No eligible nodes available")

        logger.info("trace_id=%s event=nodes_selected nodes=%s", trace_id, [n.node_id for n in selected_nodes])

        timeout = SETTINGS.node_timeout_ms / 1000

        async def _safe_run(node: BaseNode) -> CandidateAnswer:
            try:
                return await asyncio.wait_for(node.run(task), timeout=timeout)
            except Exception as exc:
                return CandidateAnswer(
                    candidate_id=generate_id("cand"),
                    task_id=task.task_id,
                    node_id=node.node_id,
                    output=None,
                    confidence_self_reported=None,
                    evidence_refs=[],
                    duration_ms=int(timeout * 1000),
                    error=f"node_runtime_error: {exc}",
                )

        candidates = await asyncio.gather(*[_safe_run(node) for node in selected_nodes])
        valid_candidates = [c for c in candidates if c.output and not c.error]

        verification = VerificationEngine.verify(task, candidates)
        if not verification.selected_candidate_id:
            vicdan = VicdanResult(task_id=task.task_id, decision="REJECT", risk_scores={}, rationale="No valid candidate selected by verification.", required_modification="Return system-safe failure message.")
            final_output = "HOPEverse could not produce a sufficiently valid response because all candidate paths inside HOPEtensor failed verification."
            total_duration_ms = int((time.perf_counter() - started) * 1000)
            Observer.persist(task, candidates, verification, vicdan, final_output, total_duration_ms)
            return FinalResponse(answer=final_output, confidence=0.0, selected_nodes=[c.node_id for c in candidates], verification_summary=verification.verification_summary, vicdan_status=vicdan.decision, trace_id=trace_id)

        selected_candidate = next((c for c in valid_candidates if c.candidate_id == verification.selected_candidate_id), None)
        if selected_candidate is None:
            selected_candidate = valid_candidates[0] if valid_candidates else None
        if selected_candidate is None:
            raise HTTPException(status_code=500, detail="Verification selected no usable candidate")

        vicdan = VicdanEngine.evaluate(task, selected_candidate.output or "")
        final_output = VicdanEngine.apply_decision(vicdan, selected_candidate.output or "")

        confidence = verification.confidence_score
        if vicdan.decision == "MODIFY":
            confidence = clamp(confidence * 0.92)
        elif vicdan.decision == "REVIEW":
            confidence = clamp(confidence * 0.80)
        elif vicdan.decision == "REJECT":
            confidence = 0.0

        if request.required_confidence is not None and confidence < request.required_confidence:
            final_output = "HOPEverse produced a response through HOPEtensor, but it did not meet the required confidence threshold.\n\n" + final_output

        total_duration_ms = int((time.perf_counter() - started) * 1000)
        Observer.persist(task, candidates, verification, vicdan, final_output, total_duration_ms)

        return FinalResponse(
            answer=final_output,
            confidence=confidence,
            selected_nodes=[c.node_id for c in candidates],
            verification_summary=verification.verification_summary,
            vicdan_status=vicdan.decision,
            trace_id=trace_id,
        )


ORCHESTRATOR = Orchestrator(NODE_REGISTRY)

# ---------- HOPEcore ----------

Horizon = Literal["immediate", "short", "medium", "long"]


@dataclass
class CivilizationGoal:
    id: str
    name: str
    category: str
    description: str
    urgency: float
    impact_score: float
    ethics_weight: float
    feasibility_score: float
    resource_efficiency: float
    time_sensitivity: float
    horizon: Horizon
    beneficiaries: int = 0
    dependencies: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemResources:
    budget: float
    people: int
    energy_capacity: float
    infrastructure_readiness: float
    data_readiness: float
    local_partnership_strength: float
    time_budget_months: int


@dataclass
class EthicsProfile:
    protect_children_weight: float = 1.0
    reduce_suffering_weight: float = 1.0
    dignity_weight: float = 1.0
    sustainability_weight: float = 1.0
    fairness_weight: float = 1.0
    long_term_weight: float = 1.0


@dataclass
class ConstraintSet:
    forbidden_categories: list[str] = field(default_factory=list)
    max_parallel_goals: int = 3
    min_ethics_threshold: float = 0.5
    prefer_fast_impact: bool = False
    require_local_readiness: bool = False


@dataclass
class GoalScore:
    goal_id: str
    final_score: float
    urgency_component: float
    impact_component: float
    ethics_component: float
    feasibility_component: float
    efficiency_component: float
    horizon_component: float
    resource_fit_component: float
    penalties: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class ResourceDecision:
    goal_id: str
    goal_name: str
    rank: int
    recommended_actions: list[str]
    required_resources: dict[str, Any]
    expected_impact: float
    confidence: float
    vicdan_alignment: str
    rationale: str


@dataclass
class PlanningOutput:
    top_goals: list[GoalScore]
    decisions: list[ResourceDecision]
    deferred_goals: list[GoalScore]
    planner_summary: str


class PlanGoalRequest(BaseModel):
    id: str
    name: str
    category: str
    description: str
    urgency: float = Field(..., ge=0.0, le=1.0)
    impact_score: float = Field(..., ge=0.0, le=1.0)
    ethics_weight: float = Field(..., ge=0.0, le=1.0)
    feasibility_score: float = Field(..., ge=0.0, le=1.0)
    resource_efficiency: float = Field(..., ge=0.0, le=1.0)
    time_sensitivity: float = Field(..., ge=0.0, le=1.0)
    horizon: Horizon
    beneficiaries: int = 0
    dependencies: list[str] = []
    risks: list[str] = []
    metadata: dict[str, Any] = {}


class PlanRequest(BaseModel):
    goals: list[PlanGoalRequest]
    resources: dict[str, Any]
    ethics: Optional[dict[str, float]] = None
    constraints: Optional[dict[str, Any]] = None


class VicdanGuard:
    @staticmethod
    def evaluate_goal(goal: CivilizationGoal, constraints: ConstraintSet) -> tuple[str, list[str]]:
        reasons: list[str] = []
        if goal.category in constraints.forbidden_categories:
            return "REJECT", [f"Forbidden category: {goal.category}"]
        if goal.ethics_weight < constraints.min_ethics_threshold:
            return "REJECT", [f"Ethics weight below threshold: {goal.ethics_weight:.2f}"]
        if "harm_to_children" in goal.risks:
            return "REJECT", ["Goal carries child-harm risk"]
        if "mass_displacement" in goal.risks:
            reasons.append("Requires strong mitigation for displacement risk")
        if "ecological_damage" in goal.risks:
            reasons.append("Requires sustainability guardrails")
        if reasons:
            return "REVIEW", reasons
        return "ACCEPT", ["No blocking ethical concerns detected"]


class HOPECorePlanner:
    def __init__(self, resources: SystemResources, ethics: EthicsProfile | None = None, constraints: ConstraintSet | None = None) -> None:
        self.resources = resources
        self.ethics = ethics or EthicsProfile()
        self.constraints = constraints or ConstraintSet()

    def _resource_fit(self, goal: CivilizationGoal) -> float:
        infra = self.resources.infrastructure_readiness
        data = self.resources.data_readiness
        partnership = self.resources.local_partnership_strength

        if goal.category in {"food", "health", "education"}:
            return min((infra + partnership) / 2, 1.0)
        if goal.category in {"energy", "manufacturing"}:
            return min((infra + self.resources.energy_capacity / 100.0) / 2, 1.0)
        if goal.category in {"governance", "ai", "logistics"}:
            return min((data + infra) / 2, 1.0)
        return min((infra + data + partnership) / 3, 1.0)

    def score_goal(self, goal: CivilizationGoal) -> GoalScore:
        penalties: list[str] = []
        notes: list[str] = []

        urgency_component = goal.urgency * 0.18
        impact_component = goal.impact_score * 0.22
        ethics_multiplier = (
            self.ethics.protect_children_weight
            + self.ethics.reduce_suffering_weight
            + self.ethics.dignity_weight
            + self.ethics.sustainability_weight
            + self.ethics.fairness_weight
            + self.ethics.long_term_weight
        ) / 6.0
        ethics_component = min(goal.ethics_weight * ethics_multiplier, 1.0) * 0.22
        feasibility_component = goal.feasibility_score * 0.16
        efficiency_component = goal.resource_efficiency * 0.10
        horizon_map = {"immediate": 1.0, "short": 0.85, "medium": 0.70, "long": 0.55}
        horizon_component = horizon_map[goal.horizon] * 0.06
        resource_fit_component = self._resource_fit(goal) * 0.06

        if self.constraints.prefer_fast_impact and goal.horizon in {"medium", "long"}:
            penalties.append("Fast-impact preference penalized longer horizon")
            horizon_component *= 0.7
        if self.constraints.require_local_readiness and self.resources.local_partnership_strength < 0.5:
            penalties.append("Local readiness required but partnership strength is low")
            resource_fit_component *= 0.6
        if goal.beneficiaries > 0 and goal.beneficiaries > self.resources.people * 1000:
            notes.append("Large beneficiary scope increases systemic leverage")

        final_score = urgency_component + impact_component + ethics_component + feasibility_component + efficiency_component + horizon_component + resource_fit_component

        return GoalScore(
            goal_id=goal.id,
            final_score=round(final_score, 4),
            urgency_component=round(urgency_component, 4),
            impact_component=round(impact_component, 4),
            ethics_component=round(ethics_component, 4),
            feasibility_component=round(feasibility_component, 4),
            efficiency_component=round(efficiency_component, 4),
            horizon_component=round(horizon_component, 4),
            resource_fit_component=round(resource_fit_component, 4),
            penalties=penalties,
            notes=notes,
        )

    def _recommended_actions(self, goal: CivilizationGoal) -> list[str]:
        base = {
            "food": ["Map underserved regions", "Launch local nutrition distribution pilots", "Pair food response with local production support"],
            "health": ["Prioritize preventive screening access", "Deploy community health routing", "Measure early outcome improvement"],
            "education": ["Identify high-need learners", "Deploy adaptive learning support", "Track retention and literacy gains"],
            "energy": ["Stabilize local energy bottlenecks", "Prioritize efficient distributed generation", "Track cost and resilience improvements"],
            "governance": ["Define transparent decision metrics", "Establish auditable contribution records", "Run trust-based feedback loops"],
            "ai": ["Deploy guarded orchestration", "Measure answer reliability and harms prevented", "Increase traceability and policy enforcement"],
        }
        return base.get(goal.category, ["Scope target population", "Run constrained pilot", "Measure impact and iterate"])

    def _required_resources(self, goal: CivilizationGoal) -> dict[str, Any]:
        return {
            "budget_estimate": round(10000 * (1.2 - goal.resource_efficiency), 2),
            "team_estimate": max(2, int(2 + (1.0 - goal.feasibility_score) * 8)),
            "time_estimate_months": {"immediate": 1, "short": 3, "medium": 6, "long": 12}[goal.horizon],
            "critical_dependencies": goal.dependencies,
        }

    def build_decision(self, goal: CivilizationGoal, score: GoalScore, rank: int) -> ResourceDecision:
        vicdan_alignment, reasons = VicdanGuard.evaluate_goal(goal, self.constraints)
        confidence = min(1.0, goal.feasibility_score * 0.35 + goal.ethics_weight * 0.25 + self._resource_fit(goal) * 0.20 + goal.resource_efficiency * 0.20)
        rationale = (
            f"Selected because it balances urgency ({goal.urgency:.2f}), impact ({goal.impact_score:.2f}), "
            f"ethics ({goal.ethics_weight:.2f}), and feasibility ({goal.feasibility_score:.2f}). "
            f"Vicdan status: {vicdan_alignment}. Notes: {'; '.join(reasons)}"
        )
        return ResourceDecision(
            goal_id=goal.id,
            goal_name=goal.name,
            rank=rank,
            recommended_actions=self._recommended_actions(goal),
            required_resources=self._required_resources(goal),
            expected_impact=round(goal.impact_score * max(goal.ethics_weight, 0.5), 4),
            confidence=round(confidence, 4),
            vicdan_alignment=vicdan_alignment,
            rationale=rationale,
        )

    def prioritize(self, goals: list[CivilizationGoal]) -> PlanningOutput:
        accepted: list[tuple[CivilizationGoal, GoalScore]] = []
        deferred: list[GoalScore] = []

        for goal in goals:
            vicdan_status, reasons = VicdanGuard.evaluate_goal(goal, self.constraints)
            score = self.score_goal(goal)
            if vicdan_status == "REJECT":
                score.penalties.extend(reasons)
                deferred.append(score)
                continue
            if vicdan_status == "REVIEW":
                score.notes.extend(reasons)
            accepted.append((goal, score))

        accepted.sort(key=lambda x: x[1].final_score, reverse=True)
        selected = accepted[: self.constraints.max_parallel_goals]
        deferred.extend(score for _, score in accepted[self.constraints.max_parallel_goals :])

        decisions = [self.build_decision(goal, score, rank=i + 1) for i, (goal, score) in enumerate(selected)]
        summary = (
            "No goals selected. Constraints or ethics filters blocked all candidates."
            if not decisions
            else f"Selected {len(decisions)} priority goals: {', '.join(d.goal_name for d in decisions)}. Deferred {len(deferred)} additional goals."
        )
        return PlanningOutput(top_goals=[score for _, score in selected], decisions=decisions, deferred_goals=deferred, planner_summary=summary)


def plan_from_request(req: PlanRequest) -> dict[str, Any]:
    resources = SystemResources(**req.resources)
    ethics = EthicsProfile(**(req.ethics or {}))
    constraints = ConstraintSet(**(req.constraints or {}))
    planner = HOPECorePlanner(resources=resources, ethics=ethics, constraints=constraints)
    goals = [CivilizationGoal(**goal.model_dump()) for goal in req.goals]
    output = planner.prioritize(goals)
    return {
        "top_goals": [asdict(x) for x in output.top_goals],
        "decisions": [asdict(x) for x in output.decisions],
        "deferred_goals": [asdict(x) for x in output.deferred_goals],
        "planner_summary": output.planner_summary,
    }




def write_reason_events_to_hopechain(trace_id: str, candidates: list[CandidateAnswer], verification: VerificationResult, vicdan: VicdanResult) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for candidate in candidates:
        preview = candidate.output or candidate.error or "No output"
        confidence = float(candidate.confidence_self_reported or 0.0)
        success = not bool(candidate.error)
        try:
            records.append(
                HOPECHAIN.record_node_execution(
                    trace_id=trace_id,
                    actor_name=candidate.node_id,
                    output_preview=preview,
                    confidence=confidence,
                    duration_ms=candidate.duration_ms,
                    success=success,
                )
            )
        except Exception as exc:
            records.append({"actor_name": candidate.node_id, "error": f"hopechain_node_write_failed: {exc}"})

    try:
        records.append(
            HOPECHAIN.record_goal_decision(
                trace_id=trace_id,
                actor_name="vicdan",
                goal_id=verification.selected_candidate_id or "no_candidate",
                rank=1,
                expected_impact=float(verification.confidence_score),
                vicdan_alignment=vicdan.decision,
            )
        )
    except Exception as exc:
        records.append({"actor_name": "vicdan", "error": f"hopechain_vicdan_write_failed: {exc}"})

    return records


def write_plan_events_to_hopechain(trace_id: str, plan_output: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for decision in plan_output.get("decisions", []):
        try:
            records.append(
                HOPECHAIN.record_goal_decision(
                    trace_id=trace_id,
                    actor_name="hopecore",
                    goal_id=decision.get("goal_id", "unknown_goal"),
                    rank=int(decision.get("rank", 0) or 0),
                    expected_impact=float(decision.get("expected_impact", 0.0) or 0.0),
                    vicdan_alignment=decision.get("vicdan_alignment", "REVIEW"),
                )
            )
        except Exception as exc:
            records.append({"actor_name": "hopecore", "goal_id": decision.get("goal_id"), "error": f"hopechain_plan_write_failed: {exc}"})
    return records




class DIDRegisterRequest(BaseModel):
    display_name: str = Field(..., min_length=2, max_length=80)
    actor_type: str = Field(default="human", min_length=2, max_length=40)


class DIDLoginRequest(BaseModel):
    did: str = Field(..., min_length=6, max_length=120)


class IdentityStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hope_identities (
                    did TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    actor_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hope_sessions (
                    token TEXT PRIMARY KEY,
                    did TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def create_identity(self, display_name: str, actor_type: str) -> dict[str, Any]:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", display_name.lower()).strip("-") or "citizen"
        did = f"did:hope:{slug}-{uuid.uuid4().hex[:8]}"
        now = utc_now()
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO hope_identities (did, display_name, actor_type, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (did, display_name, actor_type, now, now),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get_identity(did)

    def get_identity(self, did: str) -> Optional[dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM hope_identities WHERE did = ?", (did,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def create_session(self, did: str) -> str:
        token = secrets.token_hex(24)
        conn = self._connect()
        try:
            conn.execute("INSERT INTO hope_sessions (token, did, created_at) VALUES (?, ?, ?)", (token, did, utc_now()))
            conn.commit()
        finally:
            conn.close()
        return token

    def get_session(self, token: str) -> Optional[dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM hope_sessions WHERE token = ?", (token,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def reputation_for_did(self, did: str) -> dict[str, Any]:
        identity = self.get_identity(did)
        if not identity:
            raise HTTPException(status_code=404, detail="Identity not found")

        events = HOPECHAIN.db.list_recent_events(500)
        mine = [ev for ev in events if (ev.get("actor_did") == did)]
        contribution_count = len(mine)
        avg_impact = (sum(float(ev.get("impact_score") or 0) for ev in mine) / contribution_count) if contribution_count else 0.0
        trust_score = 0.5 + sum(float(ev.get("trust_delta") or 0) for ev in mine)
        trust_score = clamp(trust_score, 0.0, 1.0)
        reputation_score = clamp(0.45 + avg_impact * 0.35 + min(contribution_count / 20, 1.0) * 0.20, 0.0, 1.0)
        return {
            "identity": identity,
            "reputation_score": round(reputation_score, 4),
            "trust_score": round(trust_score, 4),
            "contribution_count": contribution_count,
            "recent_events": mine[:10],
        }


IDENTITY_STORE = IdentityStore(SETTINGS.db_path)

app = FastAPI(title=SETTINGS.app_name, version=SETTINGS.app_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, Any]:
    try:
        conn = sqlite3.connect(SETTINGS.db_path)
        conn.execute("SELECT 1")
        conn.close()
        db_status = "ok"
    except Exception:
        db_status = "error"

    return {
        "status": "ok",
        "service": SETTINGS.app_name,
        "version": SETTINGS.app_version,
        "db": db_status,
        "nodes_available": len(NODE_REGISTRY.list_enabled()),
    }


@app.get("/v1/nodes", response_model=list[NodeStatusResponse])
async def list_nodes() -> list[NodeStatusResponse]:
    return [
        NodeStatusResponse(
            node_id=node.node_id,
            node_type=node.node_type,
            capabilities=node.capabilities,
            enabled=node.enabled,
            trust_score=node.trust_score,
            reputation_score=node.reputation_score,
        )
        for node in NODE_REGISTRY.list_enabled()
    ]


@app.post("/v1/reason", response_model=ReasonResponse)
async def reason(request: ReasonRequest) -> ReasonResponse:
    result = await ORCHESTRATOR.execute_reasoning(request)

    try:
        trace = DB.get_trace(result.trace_id)
        if trace:
            candidates = [CandidateAnswer(**item) for item in DB.get_candidates_by_task(trace["task_id"])]
            verification_row = sqlite3.connect(SETTINGS.db_path)
            verification_row.row_factory = sqlite3.Row
            vr = verification_row.execute("SELECT * FROM verification_results WHERE task_id = ?", (trace["task_id"],)).fetchone()
            vc = verification_row.execute("SELECT * FROM vicdan_results WHERE task_id = ?", (trace["task_id"],)).fetchone()
            verification_row.close()

            if vr and vc:
                verification = VerificationResult(
                    task_id=vr["task_id"],
                    agreement_score=vr["agreement_score"],
                    evidence_score=vr["evidence_score"],
                    contradiction_flags=json.loads(vr["contradiction_flags_json"]),
                    confidence_score=vr["confidence_score"],
                    candidate_rankings=json.loads(vr["candidate_rankings_json"]),
                    selected_candidate_id=vr["selected_candidate_id"],
                    verification_summary=vr["verification_summary"],
                )
                vicdan = VicdanResult(
                    task_id=vc["task_id"],
                    decision=vc["decision"],
                    risk_scores=json.loads(vc["risk_scores_json"]),
                    rationale=vc["rationale"],
                    required_modification=vc["required_modification"],
                )
                write_reason_events_to_hopechain(result.trace_id, candidates, verification, vicdan)
    except Exception as exc:
        logger.warning("hopechain reason write skipped: %s", exc)

    return ReasonResponse(**result.model_dump())


@app.get("/v1/traces/{trace_id}", response_model=TraceResponse)
async def get_trace(trace_id: str) -> TraceResponse:
    trace = DB.get_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")

    candidates = DB.get_candidates_by_task(trace["task_id"])

    return TraceResponse(
        trace_id=trace["trace_id"],
        task_id=trace["task_id"],
        selected_nodes=json.loads(trace["selected_nodes_json"]),
        verification_summary=trace["verification_summary"],
        vicdan_status=trace["vicdan_status"],
        final_output=trace["final_output"],
        total_duration_ms=trace["total_duration_ms"],
        created_at=trace["created_at"],
        candidates=candidates,
    )


@app.post("/v1/plan")
async def plan(request: PlanRequest) -> dict[str, Any]:
    output = plan_from_request(request)
    trace_id = generate_id("plantrace")
    output["trace_id"] = trace_id

    try:
        output["hopechain_records"] = write_plan_events_to_hopechain(trace_id, output)
    except Exception as exc:
        logger.warning("hopechain plan write skipped: %s", exc)
        output["hopechain_records"] = [{"error": str(exc)}]

    return output

@app.get("/v1/chain/events")
async def chain_events(limit: int = 20) -> dict[str, Any]:
    return {
        "events": HOPECHAIN.db.list_recent_events(limit=limit),
        "chain_verify": HOPECHAIN.db.verify_chain(),
    }


class FoodRegion(BaseModel):
    region: str
    children_at_risk: int = Field(..., ge=0)
    food_supply: int = Field(..., ge=0)
    urgency: float = Field(..., ge=0.0, le=1.0)
    local_capacity: float = Field(..., ge=0.0, le=1.0)
    logistics: float = Field(..., ge=0.0, le=1.0)
    nutrition_quality: float = Field(default=0.5, ge=0.0, le=1.0)
    storage_readiness: float = Field(default=0.5, ge=0.0, le=1.0)


class FoodRequest(BaseModel):
    regions: list[FoodRegion]


def classify_food_action(priority_score: float, deficit: int, local_capacity: float) -> str:
    if deficit <= 0:
        return "Stable supply"
    if priority_score >= 0.80:
        return "Emergency food routing"
    if priority_score >= 0.65:
        return "Priority nutrition support"
    if local_capacity < 0.40:
        return "External support + logistics reinforcement"
    return "Monitor and local support"


@app.post("/v1/hopeverse/food/plan")
async def food_plan(request: FoodRequest) -> dict[str, Any]:
    trace_id = generate_id("foodtrace")
    results: list[dict[str, Any]] = []

    total_children = 0
    total_supply = 0
    total_deficit = 0

    for r in request.regions:
        deficit = max(0, r.children_at_risk - r.food_supply)
        deficit_ratio = deficit / max(1, r.children_at_risk)

        priority_score = (
            r.urgency * 0.30
            + deficit_ratio * 0.30
            + (1 - r.nutrition_quality) * 0.10
            + (1 - r.storage_readiness) * 0.10
            + r.local_capacity * 0.10
            + r.logistics * 0.10
        )
        priority_score = round(min(max(priority_score, 0.0), 1.0), 4)
        action = classify_food_action(priority_score, deficit, r.local_capacity)

        item = {
            "region": r.region,
            "children_at_risk": r.children_at_risk,
            "food_supply": r.food_supply,
            "deficit": deficit,
            "deficit_ratio": round(deficit_ratio, 4),
            "priority_score": priority_score,
            "action": action,
            "local_capacity": r.local_capacity,
            "logistics": r.logistics,
            "nutrition_quality": r.nutrition_quality,
            "storage_readiness": r.storage_readiness,
        }
        results.append(item)

        total_children += r.children_at_risk
        total_supply += r.food_supply
        total_deficit += deficit

    results.sort(key=lambda x: x["priority_score"], reverse=True)

    try:
        hopechain_records = []
        for idx, item in enumerate(results, start=1):
            hopechain_records.append(
                HOPECHAIN.record_goal_decision(
                    trace_id=trace_id,
                    actor_name="hopeverse_food",
                    goal_id=f"food_{item['region'].lower().replace(' ', '_')}",
                    rank=idx,
                    expected_impact=float(item["priority_score"]),
                    vicdan_alignment="ACCEPT",
                )
            )
    except Exception as exc:
        logger.warning("hopechain food write skipped: %s", exc)
        hopechain_records = [{"error": str(exc)}]

    return {
        "trace_id": trace_id,
        "mission": "No child sleeps hungry",
        "summary": {
            "regions": len(results),
            "total_children_at_risk": total_children,
            "total_supply": total_supply,
            "total_deficit": total_deficit,
        },
        "top_regions": results,
        "hopechain_records": hopechain_records,
    }


INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>HOPEverse — Civilization Operating System</title>
  <style>
    :root {
      --bg: #0b0f1a;
      --bg-2: #101827;
      --panel: rgba(255,255,255,0.06);
      --panel-strong: rgba(255,255,255,0.1);
      --text: #f5f7fb;
      --muted: #a9b4c7;
      --accent: #4da3ff;
      --accent-2: #71e4ff;
      --line: rgba(255,255,255,0.12);
      --ok: #6ee7b7;
      --warn: #fbbf24;
      --danger: #fb7185;
      --shadow: 0 20px 60px rgba(0,0,0,0.45);
      --radius: 22px;
      --max: 1240px;
    }

    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0;
      font-family: Inter, Arial, Helvetica, sans-serif;
      background:
        radial-gradient(circle at top right, rgba(77,163,255,0.18), transparent 28%),
        radial-gradient(circle at top left, rgba(113,228,255,0.08), transparent 24%),
        linear-gradient(180deg, #0b0f1a 0%, #0d1220 50%, #0b0f1a 100%);
      color: var(--text);
    }

    a { color: inherit; text-decoration: none; }

    .container {
      width: min(var(--max), calc(100% - 40px));
      margin: 0 auto;
    }

    .nav {
      position: sticky;
      top: 0;
      z-index: 50;
      backdrop-filter: blur(18px);
      background: rgba(11,15,26,0.72);
      border-bottom: 1px solid rgba(255,255,255,0.08);
    }

    .nav-inner {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 16px 0;
      gap: 24px;
    }

    .brand {
      font-size: 1.2rem;
      font-weight: 800;
      letter-spacing: 0.02em;
    }

    .brand span { color: var(--accent); }

    .nav-links {
      display: flex;
      flex-wrap: wrap;
      gap: 18px;
      color: var(--muted);
      font-size: 0.95rem;
    }

    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      border-radius: 999px;
      padding: 14px 22px;
      font-weight: 700;
      border: 1px solid transparent;
      transition: 0.2s ease;
      cursor: pointer;
    }

    .btn-primary {
      background: linear-gradient(90deg, var(--accent), var(--accent-2));
      color: white;
      box-shadow: 0 10px 30px rgba(77,163,255,0.25);
    }

    .btn-primary:hover { transform: translateY(-1px); }

    .btn-secondary {
      background: rgba(255,255,255,0.04);
      border-color: rgba(255,255,255,0.12);
      color: var(--text);
    }

    .hero {
      padding: 74px 0 40px;
    }

    .hero-grid {
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
      gap: 34px;
      align-items: center;
    }

    .eyebrow {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 8px 14px;
      border-radius: 999px;
      background: rgba(77,163,255,0.12);
      border: 1px solid rgba(77,163,255,0.26);
      color: #cde4ff;
      font-size: 0.9rem;
      font-weight: 700;
      margin-bottom: 18px;
    }

    h1 {
      font-size: clamp(2.7rem, 5vw, 5rem);
      line-height: 0.98;
      margin: 0 0 18px;
      letter-spacing: -0.04em;
    }

    .gradient {
      background: linear-gradient(90deg, #ffffff, #93c5fd 45%, #67e8f9 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }

    .lead {
      color: var(--muted);
      font-size: 1.15rem;
      line-height: 1.7;
      max-width: 760px;
      margin-bottom: 26px;
    }

    .hero-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 14px;
      margin-bottom: 22px;
    }

    .hero-metrics {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
      margin-top: 30px;
    }

    .metric, .card, .demo-panel, .flow-box, .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
    }

    .metric {
      padding: 18px;
    }

    .metric strong {
      display: block;
      font-size: 1.5rem;
      color: white;
      margin-bottom: 6px;
    }

    .metric span {
      color: var(--muted);
      font-size: 0.95rem;
    }

    .hero-visual {
      padding: 24px;
      position: relative;
      overflow: hidden;
    }

    .hero-visual::before {
      content: "";
      position: absolute;
      inset: -30% auto auto -30%;
      width: 320px;
      height: 320px;
      background: radial-gradient(circle, rgba(77,163,255,0.22), transparent 65%);
      pointer-events: none;
    }

    .visual-grid {
      display: grid;
      gap: 14px;
      position: relative;
      z-index: 1;
    }

    .visual-row {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }

    .mini-card {
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 18px;
      padding: 18px;
      min-height: 110px;
    }

    .mini-card h4 {
      margin: 0 0 8px;
      font-size: 1rem;
    }

    .mini-card p {
      margin: 0;
      color: var(--muted);
      font-size: 0.95rem;
      line-height: 1.55;
    }

    .pipeline {
      padding: 18px;
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 10px;
      align-items: center;
    }

    .pipe-node {
      padding: 14px 12px;
      text-align: center;
      border-radius: 16px;
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.12);
      font-weight: 700;
      font-size: 0.95rem;
    }

    .pipe-arrow {
      text-align: center;
      color: var(--accent);
      font-size: 1.3rem;
      font-weight: 800;
    }

    section {
      padding: 34px 0;
    }

    .section-head {
      margin-bottom: 22px;
    }

    .section-head h2 {
      font-size: clamp(2rem, 3vw, 3rem);
      margin: 0 0 10px;
      letter-spacing: -0.03em;
    }

    .section-head p {
      margin: 0;
      color: var(--muted);
      line-height: 1.7;
      max-width: 820px;
    }

    .grid-3 {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 18px;
    }

    .grid-4 {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 18px;
    }

    .card {
      padding: 22px;
    }

    .card h3 {
      margin: 0 0 10px;
      font-size: 1.15rem;
    }

    .card p, .card li {
      color: var(--muted);
      line-height: 1.65;
      font-size: 0.98rem;
    }

    .card ul {
      padding-left: 18px;
      margin: 12px 0 0;
    }

    .problem-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
    }

    .flow {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 12px;
      align-items: stretch;
    }

    .flow-box {
      padding: 18px 12px;
      text-align: center;
      display: flex;
      flex-direction: column;
      justify-content: center;
      min-height: 120px;
    }

    .flow-box strong {
      color: white;
      margin-bottom: 8px;
      font-size: 1rem;
    }

    .flow-box span {
      color: var(--muted);
      font-size: 0.92rem;
      line-height: 1.45;
    }

    .stack {
      display: grid;
      gap: 16px;
    }

    .panel {
      padding: 24px;
    }

    .demo-wrap {
      display: grid;
      grid-template-columns: 0.95fr 1.05fr;
      gap: 20px;
      align-items: start;
    }

    .demo-panel {
      padding: 24px;
    }

    .demo-panel h3 {
      margin: 0 0 16px;
      font-size: 1.2rem;
    }

    label {
      display: block;
      margin-bottom: 8px;
      color: var(--muted);
      font-size: 0.94rem;
      font-weight: 700;
    }

    textarea, input, select {
      width: 100%;
      background: rgba(255,255,255,0.04);
      color: white;
      border: 1px solid rgba(255,255,255,0.14);
      border-radius: 16px;
      padding: 14px 16px;
      font: inherit;
      outline: none;
      transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }

    textarea {
      min-height: 136px;
      resize: vertical;
      line-height: 1.55;
    }

    textarea:focus, input:focus, select:focus {
      border-color: rgba(77,163,255,0.7);
      box-shadow: 0 0 0 4px rgba(77,163,255,0.12);
    }

    .form-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 14px;
      margin-top: 14px;
    }

    .demo-actions {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 18px;
    }

    .status {
      margin-top: 16px;
      min-height: 24px;
      color: var(--muted);
      font-size: 0.95rem;
    }

    .result {
      margin-top: 18px;
      padding: 18px;
      border-radius: 18px;
      background: rgba(255,255,255,0.04);
      border: 1px solid rgba(255,255,255,0.1);
      display: grid;
      gap: 12px;
    }

    .result-block {
      padding: 14px 16px;
      border-radius: 14px;
      background: rgba(255,255,255,0.04);
      border: 1px solid rgba(255,255,255,0.08);
    }

    .result-label {
      display: block;
      font-size: 0.82rem;
      color: var(--accent-2);
      margin-bottom: 6px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-weight: 800;
    }

    .result-value {
      color: white;
      line-height: 1.6;
      white-space: pre-wrap;
      word-break: break-word;
    }

    .badge-row {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      padding: 9px 12px;
      border-radius: 999px;
      font-size: 0.88rem;
      font-weight: 700;
      border: 1px solid rgba(255,255,255,0.1);
      background: rgba(255,255,255,0.05);
    }

    .ok { color: var(--ok); }
    .warn { color: var(--warn); }
    .danger { color: var(--danger); }

    
    .plan-wrap {
      display: grid;
      grid-template-columns: 0.95fr 1.05fr;
      gap: 20px;
      align-items: start;
    }

    .plan-json {
      min-height: 220px;
      font-family: Consolas, monospace;
      font-size: 0.9rem;
    }

    .plan-summary {
      padding: 14px 16px;
      border-radius: 14px;
      background: rgba(255,255,255,0.04);
      border: 1px solid rgba(255,255,255,0.08);
      color: white;
      line-height: 1.6;
      white-space: pre-wrap;
    }



    .food-wrap {
      display: grid;
      grid-template-columns: 0.95fr 1.05fr;
      gap: 20px;
      align-items: start;
    }

    .chain-wrap {
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
      gap: 20px;
      align-items: start;
    }

    .chain-grid {
      display: grid;
      gap: 14px;
    }

    .chain-card {
      padding: 16px;
      border-radius: 16px;
      background: rgba(255,255,255,0.04);
      border: 1px solid rgba(255,255,255,0.08);
    }

    .chain-card pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: Consolas, Menlo, monospace;
      font-size: 0.84rem;
      color: #dce9ff;
    }

    .chain-rep {
      display: grid;
      gap: 12px;
    }

    .chain-rep-item {
      padding: 14px 16px;
      border-radius: 16px;
      background: rgba(255,255,255,0.04);
      border: 1px solid rgba(255,255,255,0.08);
    }

    .chain-progress {
      width: 100%;
      height: 10px;
      border-radius: 999px;
      background: rgba(255,255,255,0.08);
      overflow: hidden;
      margin-top: 8px;
    }

    .chain-progress > div {
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, #6ee7b7, #4da3ff);
    }

    .chain-meta {
      font-family: Consolas, Menlo, monospace;
      font-size: 0.82rem;
      color: #dce9ff;
      word-break: break-word;
      margin-top: 8px;
    }

    .roadmap {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 18px;
    }

    .roadmap .card strong {
      display: inline-block;
      margin-bottom: 10px;
      color: var(--accent-2);
      font-size: 0.9rem;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }

    .cta {
      padding: 34px;
      text-align: center;
      background:
        radial-gradient(circle at 50% 0%, rgba(77,163,255,0.18), transparent 35%),
        rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 28px;
      box-shadow: var(--shadow);
    }

    .cta h2 {
      margin: 0 0 12px;
      font-size: clamp(2rem, 4vw, 3.2rem);
    }

    .cta p {
      margin: 0 auto 20px;
      max-width: 760px;
      color: var(--muted);
      line-height: 1.7;
    }

    footer {
      padding: 30px 0 60px;
      color: var(--muted);
      font-size: 0.95rem;
    }

    @media (max-width: 1100px) {
      .hero-grid,
      .demo-wrap,
      .plan-wrap,
      .chain-wrap,
      .food-wrap,
      .problem-row,
      .grid-3,
      .grid-4,
      .roadmap,
      .flow {
        grid-template-columns: 1fr;
      }

      .pipeline {
        grid-template-columns: 1fr;
      }

      .pipe-arrow { display: none; }
    }

    @media (max-width: 760px) {
      .nav-links { display: none; }
      .hero { padding-top: 42px; }
      .hero-metrics,
      .form-row { grid-template-columns: 1fr; }
      .container { width: min(var(--max), calc(100% - 24px)); }
      h1 { line-height: 1.02; }
    }
  
    .intro-fade {
      opacity: 0;
      transform: translateY(16px);
      animation: introFade 900ms ease forwards;
    }

    .intro-delay-1 { animation-delay: 80ms; }
    .intro-delay-2 { animation-delay: 160ms; }
    .intro-delay-3 { animation-delay: 240ms; }

    .signature-chip {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 8px 14px;
      border-radius: 999px;
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.12);
      color: var(--muted);
      font-size: 0.9rem;
      font-weight: 700;
      margin-top: 6px;
    }

    @keyframes introFade {
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }

  </style>
</head>
<body>
  <nav class="nav">
    <div class="container nav-inner">
      <div class="brand">HOPE<span>verse</span></div>
      <div class="nav-links">
        <a href="#problem">Problem</a>
        <a href="#architecture">Architecture</a>
        <a href="#demo">Live Demo</a>
        <a href="#plan">HOPEcore Plan</a>
        <a href="#food">HOPEverse Food</a>
        <a href="#chain">HOPEchain</a>
        <a href="#identity">DID</a>
        <a href="#trust">Trust Layer</a>
        <a href="#verticals">11 Verticals</a>
        <a href="#roadmap">2030</a>
        <a href="#contact">Contact</a>
      </div>
      <a class="btn btn-secondary" href="#demo">Run Demo</a>
    </div>
  </nav>

  <header class="hero">
    <div class="container hero-grid">
      <div>
        <div class="eyebrow intro-fade">Civilization Operating System • Powered by HOPEtensor</div>
        <h1 class="intro-fade intro-delay-1">
          Build a <span class="gradient">trustable civilization stack</span>,
          not just another AI product.
        </h1>
        <p class="lead intro-fade intro-delay-2">
          HOPEverse is the civilization operating system. HOPEtensor is its intelligence engine. Together they connect reasoning, planning, identity, governance, trust, and real-world verticals into one coordinated architecture.
        </p>
        <div class="signature-chip intro-fade intro-delay-2">crafted by Erhan</div>
        <div class="hero-actions intro-fade intro-delay-3">
          <a class="btn btn-primary" href="#demo">Run Live Demo</a>
          <a class="btn btn-secondary" href="#architecture">See Architecture</a>
        </div>
        <div class="hero-metrics">
          <div class="metric">
            <strong>Multi-Node</strong>
            <span>Local, external, retrieval, and domain AI paths</span>
          </div>
          <div class="metric">
            <strong>Verification</strong>
            <span>Agreement, contradiction, evidence, and confidence</span>
          </div>
          <div class="metric">
            <strong>Vicdan</strong>
            <span>System-level ethics and governed final release</span>
          </div>
        </div>
      </div>

      <div class="hero-visual panel">
        <div class="visual-grid">
          <div class="visual-row">
            <div class="mini-card">
              <h4>Execution Layer</h4>
              <p>Not another model. A governed runtime for reasoning, verification, and policy control.</p>
            </div>
            <div class="mini-card">
              <h4>Trust Layer</h4>
              <p>Every answer comes with confidence and trace, not just raw output.</p>
            </div>
          </div>
          <div class="visual-row">
            <div class="mini-card">
              <h4>AI Agents</h4>
              <p>Transform agents from tools into trusted execution units.</p>
            </div>
            <div class="mini-card">
              <h4>Auditability</h4>
              <p>Observer captures node contributions, decisions, and final result.</p>
            </div>
          </div>
          <div class="pipeline">
            <div class="pipe-node">Request</div>
            <div class="pipe-arrow">→</div>
            <div class="pipe-node">Nodes</div>
            <div class="pipe-arrow">→</div>
            <div class="pipe-node">Verify</div>
            <div class="pipe-arrow">→</div>
            <div class="pipe-node">Vicdan</div>
            <div class="pipe-arrow">→</div>
            <div class="pipe-node">Trusted Output</div>
          </div>
        </div>
      </div>
    </div>
  </header>

  <section id="problem">
    <div class="container">
      <div class="section-head">
        <h2>The problem is not model size. It is execution architecture.</h2>
        <p>
          Today, most AI systems still run as a fragile linear chain: user → agent → output. That creates hallucination,
          weak trust, no structured disagreement handling, and almost no auditability at runtime.
        </p>
      </div>
      <div class="problem-row">
        <div class="card">
          <h3>Conventional AI Flow</h3>
          <p><strong>User → Model → Output</strong></p>
          <ul>
            <li>Single-path reasoning</li>
            <li>No internal verification</li>
            <li>No confidence signal</li>
            <li>No explicit ethics layer</li>
            <li>No decision trace</li>
          </ul>
        </div>
        <div class="card">
          <h3>HOPEverse Flow</h3>
          <p><strong>Request → Nodes → Verification → Vicdan → Trace</strong></p>
          <ul>
            <li>Multi-node reasoning</li>
            <li>Verification before release</li>
            <li>Confidence scoring</li>
            <li>System-level conscience</li>
            <li>Auditable runtime</li>
          </ul>
        </div>
      </div>
    </div>
  </section>

  <section id="architecture">
    <div class="container">
      <div class="section-head">
        <h2>Architecture</h2>
        <p>
          HOPEverse is the system. HOPEtensor is the governed multi-node intelligence engine inside it. The goal is not only trusted model output, but trusted coordination across the civilization stack.
        </p>
      </div>
      <div class="flow">
        <div class="flow-box">
          <strong>1. Request Intake</strong>
          <span>Normalize prompt, policy, context, and execution mode.</span>
        </div>
        <div class="flow-box">
          <strong>2. Node Selection</strong>
          <span>Select local, external, retrieval, or domain nodes.</span>
        </div>
        <div class="flow-box">
          <strong>3. Parallel Reasoning</strong>
          <span>Run multiple reasoning paths concurrently.</span>
        </div>
        <div class="flow-box">
          <strong>4. Verification</strong>
          <span>Compare outputs using agreement, contradiction, evidence, and structure.</span>
        </div>
        <div class="flow-box">
          <strong>5. Vicdan</strong>
          <span>Apply ethics, risk scoring, and context-aware decision control.</span>
        </div>
        <div class="flow-box">
          <strong>6. Trace</strong>
          <span>Persist node contributions, scores, decisions, and final output.</span>
        </div>
      </div>
    </div>
  </section>

  <section>
    <div class="container">
      <div class="section-head">
        <h2>Core system blocks</h2>
        <p>
          The system is modular by design, so execution, verification, ethics, and observability remain explicit rather than hidden inside one model.
        </p>
      </div>
      <div class="grid-4">
        <div class="card">
          <h3>Reasoning Nodes</h3>
          <p>Local models, external LLMs, retrieval nodes, and future domain-specific engines.</p>
        </div>
        <div class="card">
          <h3>Verification Engine</h3>
          <p>Agreement scoring, contradiction detection, evidence weighting, and confidence calculation.</p>
        </div>
        <div class="card">
          <h3>Vicdan Layer</h3>
          <p>Hard rule enforcement, risk scoring, context checks, and final decision state.</p>
        </div>
        <div class="card">
          <h3>Observer Layer</h3>
          <p>Full trace persistence: inputs, nodes, verification summary, Vicdan decision, output.</p>
        </div>
      </div>
    </div>
  </section>

  <section>
    <div class="container">
      <div class="section-head">
        <h2>Positioning</h2>
        <p>
          The market already has models, frameworks, and marketplaces. What it still lacks is a trust, identity, governance, and execution layer.
        </p>
      </div>
      <div class="grid-3">
        <div class="card">
          <h3>Models</h3>
          <p>Powerful generation, but single-path and opaque at runtime.</p>
        </div>
        <div class="card">
          <h3>Frameworks</h3>
          <p>Useful orchestration, but weak on verification, confidence, and governance.</p>
        </div>
        <div class="card">
          <h3>HOPEverse</h3>
          <p><strong>Civilization Operating System</strong> with HOPEtensor, HOPEchain, DID, Governance, and real-world vertical coordination built in.</p>
        </div>
      </div>
      <div class="panel" style="margin-top:18px; text-align:center;">
        <strong style="font-size:1.2rem; display:block; margin-bottom:8px;">Marketplace = App Store</strong>
        <span style="color:var(--muted); font-size:1.05rem;">HOPEverse = Operating System • HOPEtensor = Intelligence Engine</span>
      </div>
    </div>
  </section>

  <section id="demo">
    <div class="container">
      <div class="section-head">
        <h2>Live demo</h2>
        <p>
          This demo uses the HOPEverse runtime directly. It is designed to show how HOPEtensor, HOPEcore, HOPEchain, DID-style trust, governance, and vertical planning work together inside one system.
        </p>
      </div>
      <div class="demo-wrap">
        <div class="demo-panel">
          <h3>Run HOPEverse Intelligence</h3>
          <label for="prompt">Prompt</label>
          <textarea id="prompt">Explain why AI hallucinations happen and how to reduce them in production systems.</textarea>

          <div class="form-row">
            <div>
              <label for="policy">Policy Profile</label>
              <select id="policy">
                <option value="default">default</option>
                <option value="strict">strict</option>
                <option value="safe">safe</option>
              </select>
            </div>
            <div>
              <label for="mode">Mode</label>
              <select id="mode">
                <option value="">normal</option>
                <option value="strict">strict</option>
              </select>
            </div>
          </div>

          <div class="demo-actions">
            <button class="btn btn-primary" onclick="runDemo()">Run Live Demo</button>
            <button class="btn btn-secondary" onclick="loadSample()">Load Pitch Prompt</button>
          </div>

          <div class="status" id="status">Waiting for execution.</div>
        </div>

        <div class="demo-panel">
          <h3>Execution Output</h3>
          <div class="result">
            <div class="result-block">
              <span class="result-label">Answer</span>
              <div class="result-value" id="answer">No output yet.</div>
            </div>
            <div class="badge-row">
              <div class="badge"><span class="ok">Confidence:</span>&nbsp;<span id="confidence">-</span></div>
              <div class="badge"><span class="warn">Vicdan:</span>&nbsp;<span id="vicdan">-</span></div>
              <div class="badge"><span class="ok">Trace:</span>&nbsp;<span id="trace">-</span></div>
            </div>
            <div class="result-block">
              <span class="result-label">Selected Nodes</span>
              <div class="result-value" id="nodes">-</div>
            </div>
            <div class="result-block">
              <span class="result-label">Verification Summary</span>
              <div class="result-value" id="summary">-</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>


  <section id="plan">
    <div class="container">
      <div class="section-head">
        <h2>HOPEcore planning demo</h2>
        <p>
          Run civilization-priority planning with goals, resource constraints, and ethics weights.
          This calls <code>/v1/plan</code> and returns ranked goals, actions, confidence, and Vicdan alignment.
        </p>
      </div>
      <div class="plan-wrap">
        <div class="demo-panel">
          <h3>Run HOPEcore Plan</h3>
          <label for="planPayload">Planner Payload</label>
          <textarea id="planPayload" class="plan-json">{
  "goals": [
    {
      "id": "goal_food_001",
      "name": "Child Nutrition Access",
      "category": "food",
      "description": "Reduce child hunger through targeted nutrition routing and local support.",
      "urgency": 0.95,
      "impact_score": 0.96,
      "ethics_weight": 1.0,
      "feasibility_score": 0.82,
      "resource_efficiency": 0.76,
      "time_sensitivity": 0.95,
      "horizon": "immediate",
      "beneficiaries": 250000,
      "dependencies": ["local_warehousing", "school_networks"],
      "risks": []
    },
    {
      "id": "goal_ai_001",
      "name": "Trusted AI Public Service Layer",
      "category": "ai",
      "description": "Deploy traceable and governed AI assistance for public-impact workflows.",
      "urgency": 0.72,
      "impact_score": 0.84,
      "ethics_weight": 0.93,
      "feasibility_score": 0.86,
      "resource_efficiency": 0.83,
      "time_sensitivity": 0.66,
      "horizon": "short",
      "beneficiaries": 300000,
      "dependencies": ["policy_framework", "audit_logging"],
      "risks": []
    }
  ],
  "resources": {
    "budget": 500000,
    "people": 40,
    "energy_capacity": 70,
    "infrastructure_readiness": 0.78,
    "data_readiness": 0.74,
    "local_partnership_strength": 0.81,
    "time_budget_months": 12
  },
  "ethics": {
    "protect_children_weight": 1.0,
    "reduce_suffering_weight": 1.0,
    "dignity_weight": 0.95,
    "sustainability_weight": 0.9,
    "fairness_weight": 0.92,
    "long_term_weight": 0.88
  },
  "constraints": {
    "forbidden_categories": [],
    "max_parallel_goals": 3,
    "min_ethics_threshold": 0.55,
    "prefer_fast_impact": true,
    "require_local_readiness": false
  }
}</textarea>
          <div class="demo-actions">
            <button class="btn btn-primary" onclick="runPlan()">Run HOPEcore Plan</button>
            <button class="btn btn-secondary" onclick="loadPlanSample()">Load Default Plan</button>
          </div>
          <div class="status" id="planStatus">Waiting for planner execution.</div>
        </div>

        <div class="demo-panel">
          <h3>Planner Output</h3>
          <div class="result">
            <div class="result-block">
              <span class="result-label">Planner Summary</span>
              <div class="result-value" id="planSummary">No planning output yet.</div>
            </div>
            <div class="result-block">
              <span class="result-label">Top Decisions</span>
              <div class="result-value" id="planDecisions">-</div>
            </div>
            <div class="result-block">
              <span class="result-label">Full Planner JSON</span>
              <div class="trace-box" id="planOutput">-</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>




  <section id="food">
    <div class="container">
      <div class="section-head">
        <h2>HOPEverse Food</h2>
        <p>
          Prioritize food intervention regions so no child sleeps hungry. This calls <code>/v1/hopeverse/food/plan</code>.
        </p>
      </div>
      <div class="food-wrap">
        <div class="demo-panel">
          <h3>Run Food Plan</h3>
          <label for="foodPayload">Food Payload</label>
          <textarea id="foodPayload" class="plan-json">{
  "regions": [
    {
      "region": "Izmir",
      "children_at_risk": 1200,
      "food_supply": 800,
      "urgency": 0.92,
      "local_capacity": 0.70,
      "logistics": 0.65,
      "nutrition_quality": 0.55,
      "storage_readiness": 0.60
    },
    {
      "region": "Diyarbakir",
      "children_at_risk": 1800,
      "food_supply": 900,
      "urgency": 0.95,
      "local_capacity": 0.58,
      "logistics": 0.52,
      "nutrition_quality": 0.48,
      "storage_readiness": 0.44
    }
  ]
}</textarea>
          <div class="demo-actions">
            <button class="btn btn-primary" onclick="runFoodPlan()">Run Food Plan</button>
            <button class="btn btn-secondary" onclick="loadFoodSample()">Load Food Sample</button>
          </div>
          <div class="status" id="foodStatus">Waiting for food planning.</div>
        </div>

        <div class="demo-panel">
          <h3>Food Output</h3>
          <div class="result">
            <div class="result-block">
              <span class="result-label">Mission Summary</span>
              <div class="result-value" id="foodSummary">No food output yet.</div>
            </div>
            <div class="result-block">
              <span class="result-label">Top Regions</span>
              <div class="result-value" id="foodRegions">-</div>
            </div>
            <div class="result-block">
              <span class="result-label">Full Food JSON</span>
              <div class="trace-box" id="foodOutput">-</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <section id="identity">
    <div class="container">
      <div class="section-head">
        <h2>DID identity + reputation</h2>
        <p>HOPEverse needs a user layer, not only an event layer. This section creates a decentralized-style identity, opens a lightweight session, and reads contribution-based reputation directly from HOPEchain.</p>
      </div>
      <div class="chain-wrap">
        <div class="demo-panel">
          <h3>Create or login</h3>
          <label for="didName">Display Name</label>
          <input id="didName" value="Selim" />
          <div class="form-row">
            <div>
              <label for="didType">Actor Type</label>
              <select id="didType">
                <option value="human">human</option>
                <option value="builder">builder</option>
                <option value="operator">operator</option>
                <option value="organization">organization</option>
              </select>
            </div>
            <div>
              <label for="didValue">Existing DID</label>
              <input id="didValue" placeholder="did:hope:..." />
            </div>
          </div>
          <div class="demo-actions">
            <button class="btn btn-primary" onclick="registerDid()">Create DID</button>
            <button class="btn btn-secondary" onclick="loginDid()">Login DID</button>
            <button class="btn btn-secondary" onclick="loadDidProfile()">Load Reputation</button>
          </div>
          <div class="status" id="didStatus">No identity loaded yet.</div>
          <div class="result" style="margin-top:16px;">
            <div class="result-block">
              <span class="result-label">Access Token</span>
              <div class="result-value" id="didToken">-</div>
            </div>
            <div class="result-block">
              <span class="result-label">Current DID</span>
              <div class="result-value" id="didCurrent">-</div>
            </div>
          </div>
        </div>
        <div class="demo-panel">
          <h3>Identity reputation</h3>
          <div class="result">
            <div class="badge-row">
              <div class="badge"><span class="ok">Reputation:</span>&nbsp;<span id="didRep">-</span></div>
              <div class="badge"><span class="warn">Trust:</span>&nbsp;<span id="didTrust">-</span></div>
              <div class="badge"><span class="ok">Contributions:</span>&nbsp;<span id="didContrib">-</span></div>
            </div>
            <div class="result-block">
              <span class="result-label">Identity Summary</span>
              <div class="result-value" id="didSummary">No profile loaded.</div>
            </div>
            <div class="result-block">
              <span class="result-label">Recent DID Events</span>
              <div class="result-value" id="didEvents">-</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>


  <section id="chain">
    <div class="container">
      <div class="section-head">
        <h2>HOPEchain explorer</h2>
        <p>
          View DID-linked contribution history, signed events, reputation flow, and chain verification directly from the main dashboard.
        </p>
      </div>
      <div class="chain-wrap">
        <div class="demo-panel">
          <h3>Chain Control</h3>
          <div class="form-row">
            <div>
              <label for="chainLimit">Event Limit</label>
              <input id="chainLimit" type="number" value="20" min="1" max="200" />
            </div>
            <div>
              <label for="chainFilter">Actor / DID / Event Filter</label>
              <input id="chainFilter" placeholder="optional filter" />
            </div>
          </div>
          <div class="demo-actions">
            <button class="btn btn-primary" onclick="loadChain()">Load HOPEchain</button>
            <button class="btn btn-secondary" onclick="clearChainFilter()">Clear Filter</button>
          </div>
          <div class="status" id="chainStatus">Waiting for HOPEchain load.</div>

          <div class="result" style="margin-top:16px;">
            <div class="badge-row">
              <div class="badge"><span class="ok">Chain:</span>&nbsp;<span id="chainOk">-</span></div>
              <div class="badge"><span class="warn">Checked:</span>&nbsp;<span id="chainChecked">-</span></div>
              <div class="badge"><span class="ok">Events:</span>&nbsp;<span id="chainEventCount">-</span></div>
              <div class="badge"><span class="warn">Actors:</span>&nbsp;<span id="chainActorCount">-</span></div>
            </div>
            <div class="result-block">
              <span class="result-label">Chain Verification</span>
              <div class="result-value" id="chainVerifyText">No verification result yet.</div>
            </div>
          </div>
        </div>

        <div class="demo-panel">
          <h3>Reputation Explorer</h3>
          <div class="chain-rep" id="chainReputation">
            <div class="result-value">No reputation data loaded yet.</div>
          </div>
        </div>
      </div>

      <div class="demo-panel" style="margin-top:20px;">
        <h3>Chain Timeline</h3>
        <div class="chain-grid" id="chainTimeline">
          <div class="result-value">No chain events loaded yet.</div>
        </div>
      </div>
    </div>
  </section>




  <section id="trust">
    <div class="container">
      <div class="section-head">
        <h2>Trust & Coordination Layer</h2>
        <p>HOPEverse requires three coordinated layers to scale beyond demos: HOPEchain as trust infrastructure, DID as the identity layer, and Governance as the decision layer. Together they form trustable civilization infrastructure.</p>
      </div>
      <div class="grid-3">
        <div class="card">
          <h3>HOPEchain</h3>
          <p>Tracks verifiable impact instead of only transactions. It records resource flow, node execution, governance decisions, and measurable outcomes.</p>
          <ul>
            <li>Transparent event history</li>
            <li>Impact-oriented records</li>
            <li>Corruption and abuse reduction</li>
            <li>Auditable chain verification</li>
          </ul>
        </div>
        <div class="card">
          <h3>DID</h3>
          <p>Identity belongs to the individual, not to the platform. The layer is designed for verifiable access, reputation, contribution history, and privacy-aware service participation.</p>
          <ul>
            <li>Decentralized identity ownership</li>
            <li>Selective disclosure model</li>
            <li>Service access standardization</li>
            <li>Portable reputation foundation</li>
          </ul>
        </div>
        <div class="card">
          <h3>Governance</h3>
          <p>Hybrid governance combines AI-assisted analysis, human oversight, transparent rules, and execution feedback. It keeps scale from collapsing into either chaos or opaque centralization.</p>
          <ul>
            <li>Data → AI → Human → Decision</li>
            <li>Transparent control loops</li>
            <li>Ethical guardrails via Vicdan</li>
            <li>Operational accountability</li>
          </ul>
        </div>
      </div>
    </div>
  </section>

  <section id="verticals">
    <div class="container">
      <div class="section-head">
        <h2>11 Civilization Verticals</h2>
        <p>HOPEverse is not a single app. It is a multi-layer civilization architecture built around 11 core verticals that together form a complete system stack.</p>
      </div>
      <div class="grid-4">
        <div class="card"><h3>1. Food</h3><p>Nutrition, agriculture, and child hunger elimination.</p></div>
        <div class="card"><h3>2. Water</h3><p>Clean water access, purification, and resilient distribution.</p></div>
        <div class="card"><h3>3. Energy</h3><p>Clean, decentralized, affordable power systems.</p></div>
        <div class="card"><h3>4. Health</h3><p>Universal healthcare access and preventive systems.</p></div>
        <div class="card"><h3>5. Education</h3><p>AI-powered learning and lifelong knowledge access.</p></div>
        <div class="card"><h3>6. Housing</h3><p>Safe shelter, sustainable planning, and resilience.</p></div>
        <div class="card"><h3>7. Economy</h3><p>Fair value distribution through HOPEconomy.</p></div>
        <div class="card"><h3>8. Logistics</h3><p>Right resource, right place, right time.</p></div>
        <div class="card"><h3>9. Governance</h3><p>Transparent coordination and anti-corruption design.</p></div>
        <div class="card"><h3>10. Technology</h3><p>AI, data, automation, DID, and secure infrastructure.</p></div>
        <div class="card"><h3>11. Humanity</h3><p>Dignity, cohesion, compassion, and meaning.</p></div>
        <div class="card"><h3>Integration</h3><p>A breakthrough in one vertical strengthens the whole civilization stack.</p></div>
      </div>
    </div>
  </section>

  <section id="roadmap">
    <div class="container">
      <div class="section-head">
        <h2>2030 Roadmap</h2>
        <p>
          2030 is the first irreversible checkpoint: HOPEtensor remains the execution core, while HOPEverse expands into trust, identity, governance, and full civilization coordination.
        </p>
      </div>
      <div class="roadmap">
        <div class="card">
          <strong>2025–2027</strong>
          <h3>Foundation</h3>
          <p>Core engine deployed, first verticals activated, pilot regions launched, and trustable runtime proven.</p>
        </div>
        <div class="card">
          <strong>2027–2028</strong>
          <h3>Expansion</h3>
          <p>Food, Education, Logistics, Water, Energy, and Health systems expand across more regions with stronger AI coordination.</p>
        </div>
        <div class="card">
          <strong>2028–2029</strong>
          <h3>Integration</h3>
          <p>All major layers interoperate: HOPEcore, HOPEchain, DID, Governance, and cross-region service orchestration.</p>
        </div>
        <div class="card">
          <strong>2029–2030</strong>
          <h3>Activation</h3>
          <p>Systems become active, trusted, and repeatable across core regions. The goal is not perfection, but scalable proof of conscience-centered civilization by 2030.</p>
        </div>
      </div>
    </div>
  </section>

  <section id="contact">
    <div class="container">
      <div class="cta">
        <h2>We are not building just another AI tool. We are building HOPEverse.</h2>
        <p>
          HOPEverse is built for a future where intelligence, trust, coordination, identity, governance, and human impact must work together. HOPEtensor is the engine that makes the system think. HOPEchain, DID, Governance, and the verticals make the system real.
        </p>
        <div class="hero-actions" style="justify-content:center; margin-bottom:0;">
          <a class="btn btn-primary" href="#demo">Run Demo</a>
          <a class="btn btn-secondary" href="#architecture">Review Architecture</a>
        </div>
      </div>
    </div>
  </section>

  <footer>
    <div class="container">
      HOPEverse — Civilization Operating System powered by HOPEtensor • crafted by Erhan
    </div>
  </footer>

  <script>
    function setStatus(message, kind = "") {
      const el = document.getElementById("status");
      el.textContent = message;
      el.className = "status " + kind;
    }

    function loadSample() {
      document.getElementById("prompt").value = "Explain why single-model AI systems hallucinate and how governed multi-node execution reduces risk in production environments.";
    }


    function loadPlanSample() {
      document.getElementById("planPayload").value = `{
  "goals": [
    {
      "id": "goal_food_001",
      "name": "Child Nutrition Access",
      "category": "food",
      "description": "Reduce child hunger through targeted nutrition routing and local support.",
      "urgency": 0.95,
      "impact_score": 0.96,
      "ethics_weight": 1.0,
      "feasibility_score": 0.82,
      "resource_efficiency": 0.76,
      "time_sensitivity": 0.95,
      "horizon": "immediate",
      "beneficiaries": 250000,
      "dependencies": ["local_warehousing", "school_networks"],
      "risks": []
    },
    {
      "id": "goal_ai_001",
      "name": "Trusted AI Public Service Layer",
      "category": "ai",
      "description": "Deploy traceable and governed AI assistance for public-impact workflows.",
      "urgency": 0.72,
      "impact_score": 0.84,
      "ethics_weight": 0.93,
      "feasibility_score": 0.86,
      "resource_efficiency": 0.83,
      "time_sensitivity": 0.66,
      "horizon": "short",
      "beneficiaries": 300000,
      "dependencies": ["policy_framework", "audit_logging"],
      "risks": []
    }
  ],
  "resources": {
    "budget": 500000,
    "people": 40,
    "energy_capacity": 70,
    "infrastructure_readiness": 0.78,
    "data_readiness": 0.74,
    "local_partnership_strength": 0.81,
    "time_budget_months": 12
  },
  "ethics": {
    "protect_children_weight": 1.0,
    "reduce_suffering_weight": 1.0,
    "dignity_weight": 0.95,
    "sustainability_weight": 0.9,
    "fairness_weight": 0.92,
    "long_term_weight": 0.88
  },
  "constraints": {
    "forbidden_categories": [],
    "max_parallel_goals": 3,
    "min_ethics_threshold": 0.55,
    "prefer_fast_impact": true,
    "require_local_readiness": false
  }
}`;
    }

    async function runPlan() {
      const status = document.getElementById("planStatus");
      const summary = document.getElementById("planSummary");
      const decisions = document.getElementById("planDecisions");
      const output = document.getElementById("planOutput");

      status.textContent = "Running HOPEcore planning...";
      summary.textContent = "Planning...";
      decisions.textContent = "-";
      output.textContent = "-";

      try {
        const payload = JSON.parse(document.getElementById("planPayload").value);

        const response = await fetch("/v1/plan", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });

        if (!response.ok) {
          const text = await response.text();
          throw new Error(`Plan API error ${response.status}: ${text}`);
        }

        const data = await response.json();

        summary.textContent = data.planner_summary ?? "-";
        decisions.innerHTML = Array.isArray(data.decisions)
          ? data.decisions.map(d => `
              <div style="margin-bottom:14px;">
                <strong>#${d.rank} ${d.goal_name}</strong><br>
                Vicdan: ${d.vicdan_alignment} · Confidence: ${d.confidence}<br>
                Impact: ${d.expected_impact}<br>
                Actions: ${(d.recommended_actions || []).join(" • ")}
              </div>
            `).join("")
          : "-";
        output.textContent = JSON.stringify(data, null, 2);
        status.textContent = "Planner execution completed.";
      } catch (error) {
        summary.textContent = "Planning failed.";
        output.textContent = String(error);
        status.textContent = "Planner execution failed.";
      }
    }




    function loadFoodSample() {
      document.getElementById("foodPayload").value = `{
  "regions": [
    {
      "region": "Izmir",
      "children_at_risk": 1200,
      "food_supply": 800,
      "urgency": 0.92,
      "local_capacity": 0.70,
      "logistics": 0.65,
      "nutrition_quality": 0.55,
      "storage_readiness": 0.60
    },
    {
      "region": "Diyarbakir",
      "children_at_risk": 1800,
      "food_supply": 900,
      "urgency": 0.95,
      "local_capacity": 0.58,
      "logistics": 0.52,
      "nutrition_quality": 0.48,
      "storage_readiness": 0.44
    }
  ]
}`;
    }

    async function runFoodPlan() {
      const status = document.getElementById("foodStatus");
      const summary = document.getElementById("foodSummary");
      const regions = document.getElementById("foodRegions");
      const output = document.getElementById("foodOutput");

      status.textContent = "Running HOPEverse Food...";
      summary.textContent = "Planning...";
      regions.textContent = "-";
      output.textContent = "-";

      try {
        const payload = JSON.parse(document.getElementById("foodPayload").value);

        const response = await fetch("/v1/hopeverse/food/plan", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });

        if (!response.ok) {
          const text = await response.text();
          throw new Error(`Food API error ${response.status}: ${text}`);
        }

        const data = await response.json();

        summary.textContent =
          `Mission: ${data.mission}
` +
          `Regions: ${data.summary?.regions}
` +
          `Children at risk: ${data.summary?.total_children_at_risk}
` +
          `Total deficit: ${data.summary?.total_deficit}`;

        regions.innerHTML = Array.isArray(data.top_regions)
          ? data.top_regions.map(r => `
              <div style="margin-bottom:14px;">
                <strong>${r.region}</strong><br>
                Priority: ${r.priority_score}<br>
                Deficit: ${r.deficit}<br>
                Action: ${r.action}
              </div>
            `).join("")
          : "-";

        output.textContent = JSON.stringify(data, null, 2);
        status.textContent = "Food planning completed.";
        if (typeof loadChain === "function") setTimeout(loadChain, 250);
      } catch (error) {
        summary.textContent = "Food planning failed.";
        output.textContent = String(error);
        status.textContent = "Food planning failed.";
      }
    }


    function setDidView(data, token = null) {
      const rep = data.reputation || data;
      const identity = rep.identity || {};
      const did = identity.did || '-';
      document.getElementById("didCurrent").textContent = did;
      document.getElementById("didValue").value = did !== '-' ? did : document.getElementById("didValue").value;
      document.getElementById("didToken").textContent = token || data.access_token || localStorage.getItem("hopeverse_access_token") || '-';
      document.getElementById("didRep").textContent = rep.reputation_score != null ? `${(Number(rep.reputation_score) * 100).toFixed(1)}%` : '-';
      document.getElementById("didTrust").textContent = rep.trust_score != null ? `${(Number(rep.trust_score) * 100).toFixed(1)}%` : '-';
      document.getElementById("didContrib").textContent = rep.contribution_count ?? '-';
      document.getElementById("didSummary").textContent = identity.display_name
        ? `${identity.display_name} · ${identity.actor_type} · ${did}`
        : 'No identity summary available.';
      const events = Array.isArray(rep.recent_events) ? rep.recent_events : [];
      document.getElementById("didEvents").innerHTML = events.length
        ? events.map(ev => `<div style="margin-bottom:10px;"><strong>${escapeChainHtml(ev.event_type || '-')}</strong><br>DID: ${escapeChainHtml(ev.actor_did || '-')}<br>Impact: ${Number(ev.impact_score || 0).toFixed(2)} · Trust Δ: ${Number(ev.trust_delta || 0).toFixed(2)}</div>`).join("")
        : "-";
    }

    async function registerDid() {
      const status = document.getElementById("didStatus");
      try {
        status.textContent = "Creating DID...";
        const response = await fetch("/v1/did/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            display_name: document.getElementById("didName").value.trim(),
            actor_type: document.getElementById("didType").value
          })
        });
        if (!response.ok) throw new Error(await response.text());
        const data = await response.json();
        if (data.access_token) localStorage.setItem("hopeverse_access_token", data.access_token);
        if (data.identity?.did) localStorage.setItem("hopeverse_did", data.identity.did);
        setDidView(data, data.access_token);
        status.textContent = "DID created and session opened.";
        if (typeof loadChain === "function") setTimeout(loadChain, 200);
      } catch (error) {
        status.textContent = "DID creation failed.";
        document.getElementById("didSummary").textContent = String(error);
      }
    }

    async function loginDid() {
      const status = document.getElementById("didStatus");
      try {
        const did = document.getElementById("didValue").value.trim() || localStorage.getItem("hopeverse_did") || "";
        status.textContent = "Opening DID session...";
        const response = await fetch("/v1/did/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ did })
        });
        if (!response.ok) throw new Error(await response.text());
        const data = await response.json();
        if (data.access_token) localStorage.setItem("hopeverse_access_token", data.access_token);
        if (data.identity?.did) localStorage.setItem("hopeverse_did", data.identity.did);
        setDidView(data, data.access_token);
        status.textContent = "DID session opened.";
      } catch (error) {
        status.textContent = "DID login failed.";
        document.getElementById("didSummary").textContent = String(error);
      }
    }

    async function loadDidProfile() {
      const status = document.getElementById("didStatus");
      try {
        const did = document.getElementById("didValue").value.trim() || localStorage.getItem("hopeverse_did") || "";
        if (!did) throw new Error("No DID available.");
        status.textContent = "Loading DID reputation...";
        const response = await fetch(`/v1/did/${encodeURIComponent(did)}`);
        if (!response.ok) throw new Error(await response.text());
        const data = await response.json();
        setDidView(data);
        status.textContent = "DID reputation loaded.";
      } catch (error) {
        status.textContent = "DID profile load failed.";
        document.getElementById("didSummary").textContent = String(error);
      }
    }


    function clearChainFilter() {
      document.getElementById("chainFilter").value = "";
      loadChain();
    }

    function escapeChainHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
    }

    function computeChainReputation(events) {
      const map = new Map();

      for (const ev of events) {
        const key = ev.actor_did || ev.actor_name || "unknown";
        const current = map.get(key) || {
          actor_did: ev.actor_did || "-",
          actor_name: ev.actor_name || "-",
          actor_type: ev.actor_type || "-",
          reputation_score: 0.5,
          trust_score: 0.5,
          contribution_count: 0,
          last_event_at: ev.created_at || "-",
        };

        current.reputation_score = Math.max(0, Math.min(1, current.reputation_score + (Number(ev.impact_score || 0) * 0.08)));
        current.trust_score = Math.max(0, Math.min(1, current.trust_score + Number(ev.trust_delta || 0)));
        current.contribution_count += 1;
        current.last_event_at = ev.created_at || current.last_event_at;

        map.set(key, current);
      }

      return Array.from(map.values()).sort((a, b) => b.reputation_score - a.reputation_score);
    }

    function renderChainReputation(list) {
      const root = document.getElementById("chainReputation");
      if (!list.length) {
        root.innerHTML = '<div class="result-value">No actors matched the current filter.</div>';
        return;
      }

      root.innerHTML = list.map(item => `
        <div class="chain-rep-item">
          <strong>${escapeChainHtml(item.actor_name)}</strong><br>
          <span class="result-value">${escapeChainHtml(item.actor_type)}</span>
          <div class="chain-meta">${escapeChainHtml(item.actor_did)}</div>
          <div class="result-value" style="margin-top:8px;">Reputation: ${(item.reputation_score * 100).toFixed(1)}%</div>
          <div class="chain-progress"><div style="width:${(item.reputation_score * 100).toFixed(1)}%"></div></div>
          <div class="result-value" style="margin-top:8px;">Trust: ${(item.trust_score * 100).toFixed(1)}%</div>
          <div class="chain-progress"><div style="width:${(item.trust_score * 100).toFixed(1)}%"></div></div>
          <div class="result-value" style="margin-top:8px;">Contributions: ${item.contribution_count}</div>
        </div>
      `).join("");
    }

    function renderChainTimeline(events) {
      const root = document.getElementById("chainTimeline");
      if (!events.length) {
        root.innerHTML = '<div class="result-value">No chain events matched the current filter.</div>';
        return;
      }

      root.innerHTML = events.map(ev => `
        <div class="chain-card">
          <div class="badge-row">
            <div class="badge"><span class="ok">${escapeChainHtml(ev.event_type || "-")}</span></div>
            <div class="badge">${escapeChainHtml(ev.actor_name || "-")}</div>
            <div class="badge">${escapeChainHtml(ev.actor_type || "-")}</div>
            <div class="badge">Impact: ${Number(ev.impact_score || 0).toFixed(2)}</div>
            <div class="badge">Trust Δ: ${Number(ev.trust_delta || 0).toFixed(2)}</div>
          </div>
          <div class="chain-meta">DID: ${escapeChainHtml(ev.actor_did || "-")}</div>
          <div class="chain-meta">Hash: ${escapeChainHtml(ev.record_hash || "-")}</div>
          <div class="chain-meta">Prev: ${escapeChainHtml(ev.prev_hash || "-")}</div>
          <div class="chain-meta">Created: ${escapeChainHtml(ev.created_at || "-")}</div>
          <pre style="margin-top:10px;">${escapeChainHtml(JSON.stringify(ev.payload || {}, null, 2))}</pre>
        </div>
      `).join("");
    }

    async function loadChain() {
      const status = document.getElementById("chainStatus");
      const limit = Number(document.getElementById("chainLimit").value || 20);
      const filter = document.getElementById("chainFilter").value.trim().toLowerCase();

      status.textContent = "Loading HOPEchain...";

      try {
        const res = await fetch(`/v1/chain/events?limit=${limit}`);
        if (!res.ok) {
          const text = await res.text();
          throw new Error(`Chain API error ${res.status}: ${text}`);
        }

        const data = await res.json();
        let events = Array.isArray(data.events) ? data.events : [];

        if (filter) {
          events = events.filter(ev =>
            String(ev.actor_did || "").toLowerCase().includes(filter) ||
            String(ev.actor_name || "").toLowerCase().includes(filter) ||
            String(ev.event_type || "").toLowerCase().includes(filter)
          );
        }

        const reputation = computeChainReputation(events);
        const uniqueActors = new Set(events.map(ev => ev.actor_did || ev.actor_name)).size;

        document.getElementById("chainOk").textContent = data.chain_verify?.ok ? "VALID" : "BROKEN";
        document.getElementById("chainChecked").textContent = data.chain_verify?.checked_records ?? "-";
        document.getElementById("chainEventCount").textContent = events.length;
        document.getElementById("chainActorCount").textContent = uniqueActors;
        document.getElementById("chainVerifyText").textContent = data.chain_verify?.ok
          ? `Chain verified successfully across ${data.chain_verify.checked_records} records.`
          : (data.chain_verify?.error || "Chain verification failed.");

        renderChainReputation(reputation);
        renderChainTimeline(events);
        status.textContent = "HOPEchain loaded successfully.";
      } catch (error) {
        document.getElementById("chainOk").textContent = "ERROR";
        document.getElementById("chainChecked").textContent = "-";
        document.getElementById("chainEventCount").textContent = "-";
        document.getElementById("chainActorCount").textContent = "-";
        document.getElementById("chainVerifyText").textContent = "No verification result.";
        document.getElementById("chainReputation").innerHTML = '<div class="result-value">Unable to load reputation view.</div>';
        document.getElementById("chainTimeline").innerHTML = `<div class="result-value">${escapeChainHtml(String(error))}</div>`;
        status.textContent = "Failed to load HOPEchain.";
      }
    }


    async function runDemo() {
      const prompt = document.getElementById("prompt").value.trim();
      const policy = document.getElementById("policy").value;
      const mode = document.getElementById("mode").value;

      if (!prompt) {
        setStatus("Prompt is required.", "danger");
        return;
      }

      setStatus("Running HOPEverse intelligence flow...", "warn");
      document.getElementById("answer").textContent = "Executing...";
      document.getElementById("confidence").textContent = "-";
      document.getElementById("vicdan").textContent = "-";
      document.getElementById("trace").textContent = "-";
      document.getElementById("nodes").textContent = "-";
      document.getElementById("summary").textContent = "-";

      try {
        const response = await fetch("/v1/reason", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            prompt,
            policy_profile: policy,
            mode: mode || null
          })
        });

        if (!response.ok) {
          const text = await response.text();
          throw new Error(`API error ${response.status}: ${text}`);
        }

        const data = await response.json();

        document.getElementById("answer").textContent = data.answer ?? "-";
        document.getElementById("confidence").textContent = data.confidence ?? "-";
        document.getElementById("vicdan").textContent = data.vicdan_status ?? "-";
        document.getElementById("trace").textContent = data.trace_id ?? "-";
        document.getElementById("nodes").textContent = Array.isArray(data.selected_nodes)
          ? data.selected_nodes.join(", ")
          : "-";
        document.getElementById("summary").textContent = data.verification_summary ?? "-";

        setStatus("Execution completed. This is a verified decision output.", "ok");
      } catch (error) {
        document.getElementById("answer").textContent = "Demo failed. Make sure the single-file HOPEverse server is running and this page is opened from the same server.";
        document.getElementById("summary").textContent = String(error);
        setStatus("Execution failed. Check API runtime and CORS/network access.", "danger");
      }
    }
    window.addEventListener("load", async () => {
      const did = localStorage.getItem("hopeverse_did");
      if (did && document.getElementById("didValue")) {
        document.getElementById("didValue").value = did;
        try { await loadDidProfile(); } catch (e) {}
      }
    });

  </script>
</body>
</html>
"""




@app.post("/v1/did/register")
async def did_register(request: DIDRegisterRequest) -> dict[str, Any]:
    identity = IDENTITY_STORE.create_identity(request.display_name.strip(), request.actor_type.strip())
    token = IDENTITY_STORE.create_session(identity["did"])
    try:
        HOPECHAIN.db.add_event(
            trace_id=generate_id("didtrace"),
            event_type="identity_created",
            actor_name=identity["display_name"],
            actor_type=identity["actor_type"],
            actor_did=identity["did"],
            impact_score=0.30,
            trust_delta=0.05,
            payload={"did": identity["did"], "display_name": identity["display_name"]},
        )
    except Exception as exc:
        logger.warning("did register chain write skipped: %s", exc)
    return {"identity": identity, "access_token": token, "reputation": IDENTITY_STORE.reputation_for_did(identity["did"])}


@app.post("/v1/did/login")
async def did_login(request: DIDLoginRequest) -> dict[str, Any]:
    identity = IDENTITY_STORE.get_identity(request.did.strip())
    if not identity:
        raise HTTPException(status_code=404, detail="DID not found")
    token = IDENTITY_STORE.create_session(identity["did"])
    return {"identity": identity, "access_token": token, "reputation": IDENTITY_STORE.reputation_for_did(identity["did"])}


@app.get("/v1/did/{did}")
async def did_profile(did: str) -> dict[str, Any]:
    return IDENTITY_STORE.reputation_for_did(did)


@app.get("/v1/did/session/{token}")
async def did_session(token: str) -> dict[str, Any]:
    session = IDENTITY_STORE.get_session(token)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": session, "reputation": IDENTITY_STORE.reputation_for_did(session["did"])}

@app.get("/", response_class=HTMLResponse)
async def root() -> HTMLResponse:
    return HTMLResponse(INDEX_HTML)


@app.get("/index.html", response_class=HTMLResponse)
async def serve_index_file() -> HTMLResponse:
    return HTMLResponse(INDEX_HTML)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)
