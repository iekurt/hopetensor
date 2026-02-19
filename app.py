from fastapi import FastAPI
from pydantic import BaseModel
from typing import Dict, List
import pulp

app = FastAPI(title="HOPEtensor AI v4.3 - Weakest First Engine")

# ==========================================================
# Request Model
# ==========================================================

class IntentRequest(BaseModel):
    intent: str
    regions: List[str]
    vulnerability: Dict[str, float]
    budget: float


# ==========================================================
# Doctrine Parameters (Locked - Weakest First)
# ==========================================================

ALPHA = 0.9   # utility weight
BETA = 0.2    # inequality penalty
GAMMA = 1.6   # vulnerability dominance
DELTA = 0.3   # power concentration penalty


# ==========================================================
# LP ENGINE
# ==========================================================

def run_civilization_lp(regions, vulnerability_score, budget):

    prob = pulp.LpProblem("HOPEtensor_Civilization", pulp.LpMaximize)

    # Decision variables
    allocation = {
        r: pulp.LpVariable(f"alloc_{r}", lowBound=0)
        for r in regions
    }

    # -------------------------
    # Utility
    # -------------------------
    utility = pulp.lpSum([allocation[r] for r in regions])

    # -------------------------
    # Vulnerability Bonus
    # -------------------------
    vulnerable_bonus = pulp.lpSum([
        vulnerability_score.get(r, 0) * allocation[r]
        for r in regions
    ])

    # -------------------------
    # Power Concentration
    # -------------------------
    max_alloc = pulp.LpVariable("max_alloc", lowBound=0)
    for r in regions:
        prob += allocation[r] <= max_alloc

    power_penalty = max_alloc

    # -------------------------
    # Inequality (Pairwise Absolute Differences)
    # -------------------------
    diff_vars = []
    for i in range(len(regions)):
        for j in range(i + 1, len(regions)):
            diff = pulp.LpVariable(f"diff_{i}_{j}", lowBound=0)
            prob += allocation[regions[i]] - allocation[regions[j]] <= diff
            prob += allocation[regions[j]] - allocation[regions[i]] <= diff
            diff_vars.append(diff)

    inequality_penalty = pulp.lpSum(diff_vars)

    # -------------------------
    # Objective (Doctrine v1)
    # -------------------------
    prob += (
        ALPHA * utility
        + GAMMA * vulnerable_bonus
        - DELTA * power_penalty
        - BETA * inequality_penalty
    )

    # -------------------------
    # Budget Constraint
    # -------------------------
    prob += utility <= budget

    # Solve
    prob.solve()

    return {
        "status": pulp.LpStatus[prob.status],
        "allocation": {
            r: round(allocation[r].value(), 2)
            for r in regions
        }
    }


# ==========================================================
# Endpoint
# ==========================================================

@app.post("/civilization-optimize")
def civilization_optimize(req: IntentRequest):

    result = run_civilization_lp(
        req.regions,
        req.vulnerability,
        req.budget
    )

    return {
        "doctrine": "Weakest First",
        "parameters": {
            "alpha": ALPHA,
            "beta": BETA,
            "gamma": GAMMA,
            "delta": DELTA
        },
        "result": result
    }
