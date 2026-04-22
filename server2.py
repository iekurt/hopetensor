from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import sqlite3
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


# ============================================================
# HOPEtensor v1 - Single-File Full Rewrite
# ------------------------------------------------------------
# Purpose:
# - Governed multi-node reasoning engine
# - Parallel node execution
# - Verification scoring
# - Vicdan safety / ethics layer
# - Observer trace persistence
# - Stable API surface
#
# Endpoints:
# - GET  /health
# - GET  /v1/nodes
# - POST /v1/reason
# - GET  /v1/traces/{trace_id}
#
# Notes:
# - This file is intentionally self-contained for fast adoption.
# - SQLite is used for persistence to avoid extra dependencies.
# - One local node always works.
# - External LLM node is optional via environment variables.
# ============================================================


# ============================================================
# Configuration
# ============================================================


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
    enable_external_node: bool = env_bool("ENABLE_EXTERNAL_NODE", False)
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


# ============================================================
# Logging
# ============================================================

logging.basicConfig(
    level=getattr(logging, SETTINGS.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("hopetensor")


# ============================================================
# Utility helpers
# ============================================================


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


# ============================================================
# API Models
# ============================================================

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


class NodeStatusResponse(BaseModel):
    node_id: str
    node_type: str
    capabilities: list[str]
    enabled: bool
    trust_score: float
    reputation_score: float


# ============================================================
# Domain Models
# ============================================================

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


# ============================================================
# Database Layer
# ============================================================

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

    def list_nodes(self) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM nodes ORDER BY node_id ASC").fetchall()
            return [dict(row) for row in rows]
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

    def save_candidates(self, candidates: list[CandidateAnswer]) -> None:
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

    def save_verification(self, vr: VerificationResult) -> None:
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

    def save_vicdan(self, vc: VicdanResult) -> None:
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
            row = conn.execute(
                "SELECT * FROM traces WHERE trace_id = ?",
                (trace_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


DB = Database(SETTINGS.db_path)


# ============================================================
# Task Classification
# ============================================================

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


# ============================================================
# Node System
# ============================================================

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
            # Deterministic local fallback response.
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
        except Exception as exc:  # pragma: no cover
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
        self.enabled = SETTINGS.enable_external_node and bool(SETTINGS.external_llm_api_key)

    async def run(self, task: TaskContext) -> CandidateAnswer:
        start = time.perf_counter()
        if not self.enabled:
            return CandidateAnswer(
                candidate_id=generate_id("cand"),
                task_id=task.task_id,
                node_id=self.node_id,
                output=None,
                confidence_self_reported=None,
                evidence_refs=[],
                duration_ms=int((time.perf_counter() - start) * 1000),
                error="external_node_disabled",
            )

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
            # Placeholder retrieval behavior for v1 single-file build.
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
        except Exception as exc:  # pragma: no cover
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
        nodes = self.list_enabled()
        selected: list[BaseNode] = []

        # local node is always desirable when available for independence.
        local = [n for n in nodes if n.node_type == "local"]
        external = [n for n in nodes if n.node_type == "external_llm"]
        retrieval = [n for n in nodes if n.node_type == "retrieval"]

        if local:
            selected.append(local[0])
        if external:
            selected.append(external[0])

        if task_type == "retrieval_recommended" and retrieval:
            selected.append(retrieval[0])
        if mode == "strict" and retrieval and retrieval[0] not in selected:
            selected.append(retrieval[0])

        # Strict mode should try to satisfy min node count.
        if mode == "strict" and len(selected) < SETTINGS.strict_mode_min_nodes:
            for node in nodes:
                if node not in selected:
                    selected.append(node)
                if len(selected) >= SETTINGS.strict_mode_min_nodes:
                    break

        return selected


NODE_REGISTRY = NodeRegistry()
if SETTINGS.enable_local_node:
    NODE_REGISTRY.register(LocalNode())
NODE_REGISTRY.register(ExternalLLMNode())
if SETTINGS.enable_retrieval_node:
    NODE_REGISTRY.register(RetrievalNode())


# ============================================================
# Verification Engine
# ============================================================

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
        contradiction_markers = [
            ("must", "must not"),
            ("is", "is not"),
            ("can", "cannot"),
            ("allowed", "not allowed"),
        ]
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
    def calculate_confidence(
        cls,
        agreement_score: float,
        evidence_score: float,
        reputation_weight: float,
        structural_validity: float,
    ) -> float:
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
            confidence = cls.calculate_confidence(
                agreement_score=agreement_score,
                evidence_score=evidence_score,
                reputation_weight=reputation_weight,
                structural_validity=structural_validity,
            )
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


# ============================================================
# Vicdan Engine
# ============================================================

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
            return VicdanResult(
                task_id=task.task_id,
                decision="REJECT",
                risk_scores=risk_scores,
                rationale=hard_violation,
                required_modification="Replace with safe refusal.",
            )

        if max_risk >= 0.80:
            return VicdanResult(
                task_id=task.task_id,
                decision="REJECT",
                risk_scores=risk_scores,
                rationale="Risk score exceeded reject threshold.",
                required_modification="Replace with safe refusal.",
            )

        if max_risk >= 0.55:
            return VicdanResult(
                task_id=task.task_id,
                decision="REVIEW",
                risk_scores=risk_scores,
                rationale="Risk score exceeded review threshold.",
                required_modification="Return guarded answer with reduced operational detail.",
            )

        if max_risk >= 0.35:
            return VicdanResult(
                task_id=task.task_id,
                decision="MODIFY",
                risk_scores=risk_scores,
                rationale="Moderate risk detected; output should be softened or constrained.",
                required_modification="Return moderated answer.",
            )

        return VicdanResult(
            task_id=task.task_id,
            decision="ACCEPT",
            risk_scores=risk_scores,
            rationale="No blocking or elevated risk detected.",
            required_modification=None,
        )

    @staticmethod
    def apply_decision(vicdan: VicdanResult, selected_output: str) -> str:
        if vicdan.decision == "ACCEPT":
            return selected_output
        if vicdan.decision == "MODIFY":
            return (
                "Modified by Vicdan: the original answer was reduced to keep it high-level, non-operational, and safer.\n\n"
                + selected_output
            )
        if vicdan.decision == "REVIEW":
            return (
                "Vicdan review state: the request touches elevated-risk territory. "
                "Only a guarded, high-level response is returned.\n\n"
                + selected_output
            )
        return (
            "Vicdan rejection: the system cannot provide the requested output because it violates the active safety policy."
        )


# ============================================================
# Observer
# ============================================================

class Observer:
    @staticmethod
    def persist(
        task: TaskContext,
        candidates: list[CandidateAnswer],
        verification: VerificationResult,
        vicdan: VicdanResult,
        final_output: str,
        total_duration_ms: int,
    ) -> None:
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


# ============================================================
# Orchestrator
# ============================================================

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
            vicdan = VicdanResult(
                task_id=task.task_id,
                decision="REJECT",
                risk_scores={},
                rationale="No valid candidate selected by verification.",
                required_modification="Return system-safe failure message.",
            )
            final_output = (
                "HOPEtensor could not produce a sufficiently valid response because all candidate paths failed verification."
            )
            total_duration_ms = int((time.perf_counter() - started) * 1000)
            Observer.persist(task, candidates, verification, vicdan, final_output, total_duration_ms)
            return FinalResponse(
                answer=final_output,
                confidence=0.0,
                selected_nodes=[c.node_id for c in candidates],
                verification_summary=verification.verification_summary,
                vicdan_status=vicdan.decision,
                trace_id=trace_id,
            )

        selected_candidate = next(
            (c for c in valid_candidates if c.candidate_id == verification.selected_candidate_id),
            None,
        )
        if selected_candidate is None:
            # Defensive fallback.
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
            final_output = (
                "HOPEtensor produced a response, but it did not meet the required confidence threshold.\n\n"
                + final_output
            )

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


# ============================================================
# FastAPI App
# ============================================================

app = FastAPI(title=SETTINGS.app_name, version=SETTINGS.app_version)

from fastapi.middleware.cors import CORSMiddleware

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
    results: list[NodeStatusResponse] = []
    for node in NODE_REGISTRY.list_enabled():
        results.append(
            NodeStatusResponse(
                node_id=node.node_id,
                node_type=node.node_type,
                capabilities=node.capabilities,
                enabled=node.enabled,
                trust_score=node.trust_score,
                reputation_score=node.reputation_score,
            )
        )
    return results


@app.post("/v1/reason", response_model=ReasonResponse)
async def reason(request: ReasonRequest) -> ReasonResponse:
    result = await ORCHESTRATOR.execute_reasoning(request)
    return ReasonResponse(**result.model_dump())


@app.get("/v1/traces/{trace_id}", response_model=TraceResponse)
async def get_trace(trace_id: str) -> TraceResponse:
    trace = DB.get_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")

    return TraceResponse(
        trace_id=trace["trace_id"],
        task_id=trace["task_id"],
        selected_nodes=json.loads(trace["selected_nodes_json"]),
        verification_summary=trace["verification_summary"],
        vicdan_status=trace["vicdan_status"],
        final_output=trace["final_output"],
        total_duration_ms=trace["total_duration_ms"],
        created_at=trace["created_at"],
    )


# ============================================================
# Local runner
# ============================================================

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
