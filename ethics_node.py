from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

FORBIDDEN = ["kill", "harm", "violence", "hate"]

class EthicsRequest(BaseModel):
    task_id: str
    output: str

@app.post("/ethics")
def ethics(req: EthicsRequest):
    score = 0.95
    text = req.output.lower()
    for w in FORBIDDEN:
        if w in text:
            score = 0.2
    return {"task_id": req.task_id, "ethics_score": score, "category": "MVP", "notes": "Keyword ethics filter"}
