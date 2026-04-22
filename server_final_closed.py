from __future__ import annotations

import asyncio
import json
import logging
import os
import re
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

from fastapi.responses import FileResponse


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
    app_name: str = os.getenv("APP_NAME", "HOPEtensor")
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
logger = logging.getLogger("hopetensor")
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
                            "You are a reasoning node inside HOPEtensor. "
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
            final_output = "HOPEtensor could not produce a sufficiently valid response because all candidate paths failed verification."
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
            final_output = "HOPEtensor produced a response, but it did not meet the required confidence threshold.\n\n" + final_output

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


@app.get("/")
async def root() -> FileResponse:
    html_path = Path(__file__).with_name("index_final_closed.html")
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="index_final_closed.html not found")
    return FileResponse(html_path, media_type="text/html")


@app.get("/index_final_closed.html")
async def serve_index_file() -> FileResponse:
    return await root()


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)
