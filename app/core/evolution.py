from .engine import run_maxmin_allocation
from .config import DEFAULT_IMPACT


def run_dynamic_evolution(regions, vulnerability, budget, periods, impact=None):

    if impact is None:
        impact = DEFAULT_IMPACT

    vulnerability = vulnerability.copy()
    history = []

    for t in range(periods):

        result = run_maxmin_allocation(regions, vulnerability, budget)
        allocation = result["allocation"]

        # Update vulnerability
        for r in regions:
            vulnerability[r] = max(
                0,
                vulnerability[r] - impact * allocation[r]
            )

        history.append({
            "period": t,
            "allocation": allocation,
            "vulnerability": {
                r: round(vulnerability[r], 6)
                for r in regions
            },
            "minimum_stability": result["minimum_stability"]
        })

    return history
