import pulp
from .config import MIN_VULNERABILITY


def run_maxmin_allocation(regions, vulnerability, budget):

    prob = pulp.LpProblem("HOPEtensor_MaxMin", pulp.LpMaximize)

    allocation = {
        r: pulp.LpVariable(f"alloc_{r}", lowBound=0)
        for r in regions
    }

    z = pulp.LpVariable("z", lowBound=0)

    # Weakest-First Structural Constraint
    for r in regions:
        v = max(vulnerability.get(r, MIN_VULNERABILITY), MIN_VULNERABILITY)
        prob += allocation[r] >= z * v

    # Budget Constraint
    prob += pulp.lpSum(allocation.values()) <= budget

    # Objective
    prob += z

    prob.solve()

    if pulp.LpStatus[prob.status] != "Optimal":
        raise ValueError("Optimization did not converge")

    return {
        "minimum_stability": round(z.value(), 6),
        "allocation": {
            r: round(allocation[r].value(), 4)
            for r in regions
        }
    }
