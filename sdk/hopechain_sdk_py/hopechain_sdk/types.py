from __future__ import annotations
from typing import Any, Dict, Literal, TypedDict

PrivacyLevel = Literal["public","standard","restricted","confidential"]
TaskType = Literal["chat","embed","classify","summarize","vision","agent"]
ModelFamily = Literal["llm_tr","llm_en","multimodal","small_fast"]
VerificationProfile = Literal["standard","high_trust_required","confidential"]
Verdict = Literal["accepted","rejected","retry"]

class RequiredTrace(TypedDict):
    citations: bool
    tool_calls: bool
    safety_flags: bool
    reasoning_summary: bool

class Constraints(TypedDict):
    max_tokens: int
    temperature: float
    top_p: float
    latency_sla_ms: int
    max_cost_units: int
    privacy_level: PrivacyLevel

class Task(TypedDict):
    task_type: TaskType
    model_family: ModelFamily
    model_hint: str
    inputs: Dict[str, Any]
    constraints: Constraints
    required_trace: RequiredTrace

class Payment(TypedDict):
    mode: Literal["prepaid","postpaid"]
    budget_units: int

class TaskCreateRequest(TypedDict):
    client_did: str
    task: Task
    payment: Payment
    idempotency_key: str
