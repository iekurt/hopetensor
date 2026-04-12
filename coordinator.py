from __future__ import annotations

import json
import os
import uuid
from typing import Any
from urllib import error, request

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()


REASONING_NODES = [
    ("nodeA", os.getenv("NODE_A_REASON_URL", "http://127.0.0.1:8001/reason")),
    ("nodeB", os.getenv("NODE_B_REASON_URL", "http://127.0.0.1:8002/reason")),
]
VERIFY_URL = os.getenv("VERIFY_URL", "http://127.0.0.1:8003/verify")
ETHICS_URL = os.getenv("ETHICS_URL", "http://127.0.0.1:8004/ethics")
OBSERVER_URL = os.getenv("OBSERVER_URL", "http://127.0.0.1:8005/log")
HTTP_TIMEOUT_SECONDS = float(os.getenv("HTTP_TIMEOUT_SECONDS", "8"))


class QueryRequest(BaseModel):
    query: str
    client_did: str | None = None



def weighted_score(confidence: float, ethics_score: float, verification_score: float) -> float:
    return confidence * ethics_score * verification_score


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError("response is not a JSON object")
            return data
    except (error.URLError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail=f"Upstream call failed for {url}: {exc}") from exc


def _extract_reasoning_output(raw: dict[str, Any], *, node_id: str) -> dict[str, Any]:
    """
    Support both formats:
    - Legacy: {"node_id": "nodeA", "output": "...", "confidence": 0.8}
    - Current reasoning_node/core.py envelope: {"ok": true, "result": "...", ...}
    """
    if "output" in raw:
        output = str(raw.get("output", ""))
        confidence = float(raw.get("confidence", 0.8))
        src_node_id = str(raw.get("node_id", node_id))
    else:
        output = str(raw.get("result", ""))
        confidence = float(raw.get("confidence", 0.8))
        src_node_id = node_id

    if not output.strip():
        raise ValueError(f"Empty reasoning output from {src_node_id}")

    return {
        "node_id": src_node_id,
        "output": output,
        "confidence": confidence,
    }


@app.post("/query")
def query(req: QueryRequest):
    task_id = str(uuid.uuid4())
    q = req.query.strip()
    if not q:
        raise HTTPException(status_code=400, detail="query must not be empty")

    responses = []
    for node_id, url in REASONING_NODES:
        raw = _post_json(url, {"text": q, "trace": True})
        try:
            normalized = _extract_reasoning_output(raw, node_id=node_id)
        except ValueError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        responses.append(normalized)

    outputs = [r["output"] for r in responses]

    ver = _post_json(VERIFY_URL, {"task_id": task_id, "outputs": outputs})
    verification_score = float(ver.get("verification_score", 0.0))

    # MVP behavior: ethics score from first output
    eth = _post_json(ETHICS_URL, {"task_id": task_id, "output": outputs[0]})
    ethics_score = float(eth.get("ethics_score", 0.0))

    scored: list[tuple[float, dict[str, Any]]] = []
    for r in responses:
        s = weighted_score(float(r["confidence"]), ethics_score, verification_score)
        scored.append((s, r))
    scored.sort(key=lambda x: x[0], reverse=True)

    best_score, best = scored[0]

    _post_json(
        OBSERVER_URL,
        {
            "task_id": task_id,
            "data": {
                "query": q,
                "responses": responses,
                "verification": ver,
                "ethics": eth,
                "consensus": {"output": best["output"], "score": best_score},
                "all_scores": [{"node": r["node_id"], "score": s} for s, r in scored],
            },
        },
    )

    return {
        "request_id": request_id,
        "task_id": task_id,
        "client_did": client_did or None,
        "final_output": best["output"],
        "final_score": best_score,
        "meta": {
            "verification": ver,
            "ethics": eth,
            "scores": [{"node": r["node_id"], "score": s} for s, r in scored],
        },
    }
