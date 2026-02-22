from fastapi import FastAPI, HTTPException
from .models import AllocationRequest, DynamicRequest
from .core.engine import run_maxmin_allocation
from .core.evolution import run_dynamic_evolution
from .utils.validation import validate_regions

app = FastAPI(
    title="HOPEtensor",
    version="0.3.0",
    description="Core Ethical Optimization Engine — Weakest First Doctrine"
)


@app.post("/deep-rise")
def deep_rise(req: AllocationRequest):
    try:
        validate_regions(req.regions, req.vulnerability)
        result = run_maxmin_allocation(
            req.regions,
            req.vulnerability,
            req.budget
        )
        return {
            "engine": "Max–Min Civilization Core",
            "doctrine": "Weakest First",
            "result": result
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/dynamic-deep-rise")
def dynamic_deep_rise(req: DynamicRequest):
    try:
        validate_regions(req.regions, req.vulnerability)
        history = run_dynamic_evolution(
            req.regions,
            req.vulnerability,
            req.budget,
            req.periods,
            req.impact
        )
        return {
            "engine": "Dynamic Civilization Core",
            "doctrine": "Weakest First",
            "history": history
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
