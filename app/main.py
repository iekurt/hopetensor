from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class TaskCreate(BaseModel):
    type: str = Field(..., examples=["generate_text"])
    payload: dict[str, Any] = Field(default_factory=dict)


class TaskResponse(BaseModel):
    id: str
    type: str
    payload: dict[str, Any]
    status: TaskStatus
    result: Any | None = None
    error: str | None = None
    created_at: str
    updated_at: str


class TaskStore:
    def __init__(self) -> None:
        self.tasks: dict[str, TaskResponse] = {}
        self.queue: asyncio.Queue[str] = asyncio.Queue()

    async def create_task(self, data: TaskCreate) -> TaskResponse:
        task_id = str(uuid.uuid4())
        now = utc_now()

        task = TaskResponse(
            id=task_id,
            type=data.type,
            payload=data.payload,
            status=TaskStatus.pending,
            result=None,
            error=None,
            created_at=now,
            updated_at=now,
        )

        self.tasks[task_id] = task
        await self.queue.put(task_id)
        return task

    def get_task(self, task_id: str) -> TaskResponse | None:
        return self.tasks.get(task_id)

    def list_tasks(self) -> list[TaskResponse]:
        return list(self.tasks.values())

    def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        result: Any | None = None,
        error: str | None = None,
    ) -> None:
        task = self.tasks.get(task_id)
        if not task:
            return

        task.status = status
        task.updated_at = utc_now()

        if result is not None:
            task.result = result

        if error is not None:
            task.error = error


store = TaskStore()
worker_task: asyncio.Task | None = None


async def process_task(task: TaskResponse) -> Any:
    """
    Buraya gerçek iş mantığını koyacaksın.
    Şimdilik demo amaçlı birkaç task type destekliyor.
    """
    await asyncio.sleep(2)

    if task.type == "generate_text":
        prompt = str(task.payload.get("prompt", "")).strip()
        if not prompt:
            raise ValueError("payload.prompt is required for generate_text")

        return {
            "message": f"Generated response for: {prompt}",
            "length": len(prompt),
        }

    if task.type == "sum_numbers":
        numbers = task.payload.get("numbers", [])
        if not isinstance(numbers, list):
            raise ValueError("payload.numbers must be a list")

        total = sum(float(x) for x in numbers)
        return {
            "numbers": numbers,
            "total": total,
        }

    raise ValueError(f"Unsupported task type: {task.type}")


async def worker_loop() -> None:
    while True:
        task_id = await store.queue.get()
        task = store.get_task(task_id)

        if task is None:
            store.queue.task_done()
            continue

        try:
            store.update_status(task_id, TaskStatus.running)
            result = await process_task(task)
            store.update_status(task_id, TaskStatus.completed, result=result)
        except Exception as exc:
            store.update_status(task_id, TaskStatus.failed, error=str(exc))
        finally:
            store.queue.task_done()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global worker_task
    worker_task = asyncio.create_task(worker_loop())
    yield
    if worker_task:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="HOPEtensor", version="0.1.0", lifespan=lifespan)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "HOPEtensor is alive"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/tasks", response_model=TaskResponse, status_code=201)
async def create_task(task: TaskCreate) -> TaskResponse:
    return await store.create_task(task)


@app.get("/v1/tasks", response_model=list[TaskResponse])
async def list_tasks() -> list[TaskResponse]:
    return store.list_tasks()


@app.get("/v1/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str) -> TaskResponse:
    task = store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
