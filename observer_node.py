from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class LogRequest(BaseModel):
    task_id: str
    data: dict

@app.post("/log")
def log(req: LogRequest):
    print("\n[OBSERVER LOG]", req.task_id)
    for k, v in req.data.items():
        print(f"- {k}: {v}")
    return {"status": "ok"}
