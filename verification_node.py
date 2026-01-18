from fastapi import FastAPI
from pydantic import BaseModel
from typing import List

app = FastAPI()

class VerifyRequest(BaseModel):
    task_id: str
    outputs: List[str]

@app.post("/verify")
def verify(req: VerifyRequest):
    score = 0.7
    if len(req.outputs) >= 2:
        # primitive consistency: if key term overlaps
        common = set(req.outputs[0].lower().split()).intersection(set(req.outputs[1].lower().split()))
        if len(common) > 3:
            score = 0.85
    return {"task_id": req.task_id, "verification_score": score, "notes": "MVP heuristic verification"}
