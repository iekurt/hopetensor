from fastapi import FastAPI
from pydantic import BaseModel
import requests
import uuid

app = FastAPI()

REASONING_NODES = [
    ("nodeA", "http://127.0.0.1:8001/reason"),
    ("nodeB", "http://127.0.0.1:8002/reason"),
]
VERIFY_URL = "http://127.0.0.1:8003/verify"
ETHICS_URL = "http://127.0.0.1:8004/ethics"
OBSERVER_URL = "http://127.0.0.1:8005/log"

class QueryRequest(BaseModel):
    query: str

def weighted_score(confidence, ethics_score, verification_score):
    return confidence * ethics_score * verification_score

@app.post("/query")
def query(req: QueryRequest):
    task_id = str(uuid.uuid4())
    q = req.query

    # 1) reasoning collection
    responses = []
    for node_id, url in REASONING_NODES:
        r = requests.post(url, json={"task_id": task_id, "query": q, "node_id": node_id}).json()
        responses.append(r)

    outputs = [r["output"] for r in responses]

    # 2) verification score
    ver = requests.post(VERIFY_URL, json={"task_id": task_id, "outputs": outputs}).json()
    verification_score = ver["verification_score"]

    # 3) ethics score (MVP: apply on first output)
    eth = requests.post(ETHICS_URL, json={"task_id": task_id, "output": outputs[0]}).json()
    ethics_score = eth["ethics_score"]

    # 4) consensus scoring
    scored = []
    for r in responses:
        s = weighted_score(r["confidence"], ethics_score, verification_score)
        scored.append((s, r))
    scored.sort(key=lambda x: x[0], reverse=True)

    best_score, best = scored[0]

    # 5) observer
    requests.post(OBSERVER_URL, json={
        "task_id": task_id,
        "data": {
            "query": q,
            "responses": responses,
            "verification": ver,
            "ethics": eth,
            "consensus": {"output": best["output"], "score": best_score},
            "all_scores": [{"node": r["node_id"], "score": s} for s, r in scored]
        }
    })

    return {
        "task_id": task_id,
        "final_output": best["output"],
        "final_score": best_score,
        "meta": {
            "verification": ver,
            "ethics": eth,
            "scores": [{"node": r["node_id"], "score": s} for s, r in scored]
        }
    }
