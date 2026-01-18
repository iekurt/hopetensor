from fastapi import FastAPI
from pydantic import BaseModel
import random

app = FastAPI()


class TaskRequest(BaseModel):
    task_id: str
    query: str
    node_id: str


@app.post("/reason")
def reason(req: TaskRequest):
    templates = [
        f"[{req.node_id}] {req.query} -> (mock) HOPE is a decentralized goodness system.",
        f"[{req.node_id}] {req.query} -> (mock) HOPE combines economy, technology and conscience.",
        f"[{req.node_id}] {req.query} -> (mock) HOPE 2050 proposes a three-world model.",
    ]
    output = random.choice(templates)
    confidence = round(random.uniform(0.6, 0.95), 3)
    return {
        "task_id": req.task_id,
        "node_id": req.node_id,
        "output": output,
        "confidence": confidence,
    }
