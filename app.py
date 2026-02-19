from fastapi import FastAPI
from pydantic import BaseModel
from typing import Dict, List
import pulp

app = FastAPI(title="HOPEtensor v6 - Dynamic Civilization Engine")


class DynamicRequest(BaseModel):
    regions: List[str]
    vulnerability: Dict[str, float]
    budget: float
    periods: int
    impact: float   # k coefficient


def run_period(regions, vulnerability, budget):

    prob = pulp.LpProblem("Deep_Rise_Period", pulp.LpMaximize)

    allocation = {
        r: pulp.LpVariable(f"alloc_{r}", lowBound=0)
        for r in regions
    }

    z = pulp.LpVariable("z", lowBound=0)

    for r in regions:
        v = max(vulnerability.get(r, 0.0001), 0.0001)
        prob += allocation[r] >= z * v

    prob += pulp.lpSum(allocation.values()) <= budget

    prob += z
    prob.solve()

    return {r: allocation[r].value() for r in regions}


@app.post("/dynamic-deep-rise")
def dynamic_deep_rise(req: DynamicRequest):

    regions = req.regions
    vulnerability = req.vulnerability.copy()
    history = []

    for t in range(req.periods):

        allocation = run_period(regions, vulnerability, req.budget)

        # Update vulnerability
        for r in regions:
            vulnerability[r] = max(
                0,
                vulnerability[r] - req.impact * allocation[r]
            )

        history.append({
            "period": t,
            "allocation": {r: round(allocation[r], 2) for r in regions},
            "vulnerability": {r: round(vulnerability[r], 4) for r in regions}
        })

    return {
        "engine": "Dynamic Deep Rise",
        "history": history
    }
