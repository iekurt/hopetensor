import pulp
from decimal import Decimal
from .config import MIN_VULNERABILITY
from app.core.math.precision import to_decimal, round_decimal

def run_maxmin_allocation(regions, vulnerability, budget):

    # ---- INPUT SANITIZATION ----
    budget = float(to_decimal(budget))

    sanitized_vulnerability = {}
    for r in regions:
        v_raw = vulnerability.get(r, MIN_VULNERABILITY)
        v_dec = to_decimal(v_raw)
        min_v = to_decimal(MIN_VULNERABILITY)
        sanitized_vulnerability[r] = float(max(v_dec, min_v))

    # ---- OPT MODEL ----
    prob = pulp.LpProblem("HOPEtensor_MaxMin", pulp.LpMaximize)

    allocation = {
        r: pulp.LpVariable(f"alloc_{r}", lowBound=0)
        for r in regions
    }

    z = pulp.LpVariable("z", lowBound=0)

    for r in regions:
        prob += allocation[r] >= z * sanitized_vulnerability[r]

    prob += pulp.lpSum(allocation.values()) <= budget
    prob += z

    prob.solve()

    if pulp.LpStatus[prob.status] != "Optimal":
        raise ValueError("Optimization did not converge")

    # ---- OUTPUT HARDENING ----
    z_val = round_decimal(to_decimal(z.value()), 6)

    allocation_result = {
        r: round_decimal(to_decimal(allocation[r].value()), 4)
        for r in regions
    }

    return {
        "minimum_stability": float(z_val),
        "allocation": {r: float(allocation_result[r]) for r in regions}
    }
