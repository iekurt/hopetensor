from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Any, Dict, List
from uuid import uuid4
from datetime import datetime, timezone
import time

APP_NAME = "HOPEtensor"
APP_VERSION = "0.3.3"

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="HOPEtensor Core API"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_trace(step: str, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "step": step,
        "at": now_iso(),
        "meta": meta or {}
    }


class AllocationRequest(BaseModel):
    regions: List[str]
    vulnerability: List[float]
    budget: float


class DynamicRequest(BaseModel):
    regions: List[str]
    vulnerability: List[float]
    budget: float
    periods: int
    impact: float


class TaskInput(BaseModel):
    text: str


class TaskConstraints(BaseModel):
    max_latency_ms: Optional[int] = 5000
    require_trace: Optional[bool] = True


class TaskRequest(BaseModel):
    client_did: Optional[str] = "did:hope:user:anonymous"
    task_type: str = Field(default="reasoning")
    input: TaskInput
    constraints: Optional[TaskConstraints] = TaskConstraints()


class TaskResult(BaseModel):
    output_text: str


class TaskError(BaseModel):
    code: str
    message: str


class TaskResponse(BaseModel):
    request_id: str
    ok: bool
    result: Optional[TaskResult] = None
    trace: List[Dict[str, Any]] = []
    meta: Dict[str, Any] = {}
    error: Optional[TaskError] = None


def validate_regions(regions: List[str], vulnerability: List[float]) -> None:
    if not regions:
        raise ValueError("regions must not be empty")
    if not vulnerability:
        raise ValueError("vulnerability must not be empty")
    if len(regions) != len(vulnerability):
        raise ValueError("regions and vulnerability must have the same length")
    if any(v < 0 for v in vulnerability):
        raise ValueError("vulnerability values must be non-negative")


def run_maxmin_allocation(
    regions: List[str],
    vulnerability: List[float],
    budget: float
) -> Dict[str, Any]:
    validate_regions(regions, vulnerability)

    total_vulnerability = sum(vulnerability)
    if total_vulnerability <= 0:
        per_region = budget / len(regions)
        allocation = {region: round(per_region, 4) for region in regions}
    else:
        allocation = {
            region: round((v / total_vulnerability) * budget, 4)
            for region, v in zip(regions, vulnerability)
        }

    weakest_index = max(range(len(vulnerability)), key=lambda i: vulnerability[i])

    return {
        "budget": budget,
        "priority_region": regions[weakest_index],
        "allocation": allocation
    }


def run_dynamic_evolution(
    regions: List[str],
    vulnerability: List[float],
    budget: float,
    periods: int,
    impact: float
) -> List[Dict[str, Any]]:
    validate_regions(regions, vulnerability)

    current = [float(v) for v in vulnerability]
    history: List[Dict[str, Any]] = []

    for period in range(1, periods + 1):
        total = sum(current)
        if total <= 0:
            allocation_values = [budget / len(regions)] * len(regions)
        else:
            allocation_values = [(v / total) * budget for v in current]

        allocation = {
            region: round(value, 4)
            for region, value in zip(regions, allocation_values)
        }

        weakest_index = max(range(len(current)), key=lambda i: current[i])

        history.append({
            "period": period,
            "priority_region": regions[weakest_index],
            "allocation": allocation,
            "vulnerability_before": {
                region: round(value, 4)
                for region, value in zip(regions, current)
            }
        })

        next_current = []
        for v, alloc in zip(current, allocation_values):
            reduced = max(0.0, v - (alloc * impact))
            next_current.append(reduced)
        current = next_current

    return history


class LocalWorker:
    name = "local_stub"

    def run(self, text: str) -> str:
        text = text.strip()
        if not text:
            return "Empty input received."
        return f"HOPEtensor says: {text}"


class Coordinator:
    def __init__(self):
        self.worker = LocalWorker()

    def select_worker(self, task: TaskRequest) -> str:
        return self.worker.name

    def execute(self, task: TaskRequest) -> TaskResponse:
        request_id = f"req_{uuid4().hex[:12]}"
        trace: List[Dict[str, Any]] = []
        started = time.perf_counter()

        try:
            trace.append(make_trace("task_received", {
                "task_type": task.task_type,
                "client_did": task.client_did
            }))

            engine = self.select_worker(task)

            trace.append(make_trace("routed", {
                "engine": engine,
                "reason": "single_app_mvp"
            }))

            output = self.worker.run(task.input.text)

            latency_ms = int((time.perf_counter() - started) * 1000)

            trace.append(make_trace("completed", {
                "latency_ms": latency_ms
            }))

            return TaskResponse(
                request_id=request_id,
                ok=True,
                result=TaskResult(output_text=output),
                trace=trace if task.constraints and task.constraints.require_trace else [],
                meta={
                    "engine": engine,
                    "latency_ms": latency_ms,
                    "version": APP_VERSION
                },
                error=None
            )

        except Exception as e:
            latency_ms = int((time.perf_counter() - started) * 1000)

            trace.append(make_trace("failed", {
                "reason": "worker_exception",
                "detail": str(e),
                "latency_ms": latency_ms
            }))

            return TaskResponse(
                request_id=request_id,
                ok=False,
                result=None,
                trace=trace if task.constraints and task.constraints.require_trace else [],
                meta={
                    "version": APP_VERSION,
                    "latency_ms": latency_ms
                },
                error=TaskError(
                    code="WORKER_ERROR",
                    message="Task execution failed"
                )
            )


coordinator = Coordinator()


@app.get("/")
def root():
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "status": "ok",
        "message": "HOPEtensor — Reasoning Infrastructure"
    }


@app.get("/health")
def health():
    return "ok"


@app.get("/routes")
def routes():
    return {
        "routes": [
            "/",
            "/health",
            "/routes",
            "/deep-rise",
            "/dynamic-deep-rise",
            "/v1/tasks"
        ]
    }


@app.post("/deep-rise")
def deep_rise(req: AllocationRequest):
    try:
        result = run_maxmin_allocation(
            req.regions,
            req.vulnerability,
            req.budget
        )
        return {
            "engine": "Max-Min Civilization Core",
            "doctrine": "Weakest First",
            "result": result
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/dynamic-deep-rise")
def dynamic_deep_rise(req: DynamicRequest):
    try:
        history = run_dynamic_evolution(
            req.regions,
            req.vulnerability,
            req.budget,
            req.periods,
            req.impact
        )
        return {
            "engine": "Dynamic Civilization Core",
            "doctrine": "Weakest First",
            "history": history
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/v1/tasks", response_model=TaskResponse)
def create_task(task: TaskRequest):
    return coordinator.execute(task)
