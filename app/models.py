from pydantic import BaseModel
from typing import Dict, List


class AllocationRequest(BaseModel):
    regions: List[str]
    vulnerability: Dict[str, float]
    budget: float


class DynamicRequest(BaseModel):
    regions: List[str]
    vulnerability: Dict[str, float]
    budget: float
    periods: int
    impact: float | None = None
