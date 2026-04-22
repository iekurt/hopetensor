from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Literal
import json


Horizon = Literal["immediate", "short", "medium", "long"]


@dataclass
class CivilizationGoal:
    id: str
    name: str
    category: str
    description: str
    urgency: float
    impact_score: float
    ethics_weight: float
    feasibility_score: float
    resource_efficiency: float
    time_sensitivity: float
    horizon: Horizon
    beneficiaries: int = 0
    dependencies: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemResources:
    budget: float
    people: int
    energy_capacity: float
    infrastructure_readiness: float
    data_readiness: float
    local_partnership_strength: float
    time_budget_months: int


@dataclass
class EthicsProfile:
    protect_children_weight: float = 1.0
    reduce_suffering_weight: float = 1.0
    dignity_weight: float = 1.0
    sustainability_weight: float = 1.0
    fairness_weight: float = 1.0
    long_term_weight: float = 1.0


@dataclass
class ConstraintSet:
    forbidden_categories: list[str] = field(default_factory=list)
    max_parallel_goals: int = 3
    min_ethics_threshold: float = 0.5
    prefer_fast_impact: bool = False
    require_local_readiness: bool = False


@dataclass
class GoalScore:
    goal_id: str
    final_score: float
    urgency_component: float
    impact_component: float
    ethics_component: float
    feasibility_component: float
    efficiency_component: float
    horizon_component: float
    resource_fit_component: float
    penalties: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class ResourceDecision:
    goal_id: str
    goal_name: str
    rank: int
    recommended_actions: list[str]
    required_resources: dict[str, Any]
    expected_impact: float
    confidence: float
    vicdan_alignment: str
    rationale: str


@dataclass
class PlanningOutput:
    top_goals: list[GoalScore]
    decisions: list[ResourceDecision]
    deferred_goals: list[GoalScore]
    planner_summary: str


class VicdanGuard:
    @staticmethod
    def evaluate_goal(goal: CivilizationGoal, constraints: ConstraintSet) -> tuple[str, list[str]]:
        reasons: list[str] = []

        if goal.category in constraints.forbidden_categories:
            return "REJECT", [f"Forbidden category: {goal.category}"]

        if goal.ethics_weight < constraints.min_ethics_threshold:
            return "REJECT", [f"Ethics weight below threshold: {goal.ethics_weight:.2f}"]

        if "harm_to_children" in goal.risks:
            return "REJECT", ["Goal carries child-harm risk"]

        if "mass_displacement" in goal.risks:
            reasons.append("Requires strong mitigation for displacement risk")

        if "ecological_damage" in goal.risks:
            reasons.append("Requires sustainability guardrails")

        if reasons:
            return "REVIEW", reasons

        return "ACCEPT", ["No blocking ethical concerns detected"]


class HOPECorePlanner:
    def __init__(
        self,
        resources: SystemResources,
        ethics: EthicsProfile | None = None,
        constraints: ConstraintSet | None = None,
    ) -> None:
        self.resources = resources
        self.ethics = ethics or EthicsProfile()
        self.constraints = constraints or ConstraintSet()

    def score_goal(self, goal: CivilizationGoal) -> GoalScore:
        penalties: list[str] = []
        notes: list[str] = []

        urgency_component = goal.urgency * 0.18
        impact_component = goal.impact_score * 0.22

        ethics_multiplier = (
            self.ethics.protect_children_weight
            + self.ethics.reduce_suffering_weight
            + self.ethics.dignity_weight
            + self.ethics.sustainability_weight
            + self.ethics.fairness_weight
            + self.ethics.long_term_weight
        ) / 6.0
        ethics_component = min(goal.ethics_weight * ethics_multiplier, 1.0) * 0.22

        feasibility_component = goal.feasibility_score * 0.16
        efficiency_component = goal.resource_efficiency * 0.10

        horizon_map = {
            "immediate": 1.0,
            "short": 0.85,
            "medium": 0.70,
            "long": 0.55,
        }
        horizon_component = horizon_map[goal.horizon] * 0.06

        resource_fit = self._resource_fit(goal)
        resource_fit_component = resource_fit * 0.06

        if self.constraints.prefer_fast_impact and goal.horizon in {"medium", "long"}:
            penalties.append("Fast-impact preference penalized longer horizon")
            horizon_component *= 0.7

        if self.constraints.require_local_readiness and self.resources.local_partnership_strength < 0.5:
            penalties.append("Local readiness required but partnership strength is low")
            resource_fit_component *= 0.6

        if goal.beneficiaries > 0 and goal.beneficiaries > self.resources.people * 1000:
            notes.append("Large beneficiary scope increases systemic leverage")

        final_score = (
            urgency_component
            + impact_component
            + ethics_component
            + feasibility_component
            + efficiency_component
            + horizon_component
            + resource_fit_component
        )

        return GoalScore(
            goal_id=goal.id,
            final_score=round(final_score, 4),
            urgency_component=round(urgency_component, 4),
            impact_component=round(impact_component, 4),
            ethics_component=round(ethics_component, 4),
            feasibility_component=round(feasibility_component, 4),
            efficiency_component=round(efficiency_component, 4),
            horizon_component=round(horizon_component, 4),
            resource_fit_component=round(resource_fit_component, 4),
            penalties=penalties,
            notes=notes,
        )

    def _resource_fit(self, goal: CivilizationGoal) -> float:
        infra = self.resources.infrastructure_readiness
        data = self.resources.data_readiness
        partnership = self.resources.local_partnership_strength

        if goal.category in {"food", "health", "education"}:
            return min((infra + partnership) / 2, 1.0)

        if goal.category in {"energy", "manufacturing"}:
            return min((infra + self.resources.energy_capacity / 100.0) / 2, 1.0)

        if goal.category in {"governance", "ai", "logistics"}:
            return min((data + infra) / 2, 1.0)

        return min((infra + data + partnership) / 3, 1.0)

    def build_decision(self, goal: CivilizationGoal, score: GoalScore, rank: int) -> ResourceDecision:
        vicdan_alignment, reasons = VicdanGuard.evaluate_goal(goal, self.constraints)

        recommended_actions = self._recommended_actions(goal)
        required_resources = self._required_resources(goal)
        confidence = min(
            1.0,
            (
                goal.feasibility_score * 0.35
                + goal.ethics_weight * 0.25
                + self._resource_fit(goal) * 0.20
                + goal.resource_efficiency * 0.20
            ),
        )

        rationale = (
            f"Selected because it balances urgency ({goal.urgency:.2f}), impact ({goal.impact_score:.2f}), "
            f"ethics ({goal.ethics_weight:.2f}), and feasibility ({goal.feasibility_score:.2f}). "
            f"Vicdan status: {vicdan_alignment}. Notes: {'; '.join(reasons)}"
        )

        return ResourceDecision(
            goal_id=goal.id,
            goal_name=goal.name,
            rank=rank,
            recommended_actions=recommended_actions,
            required_resources=required_resources,
            expected_impact=round(goal.impact_score * max(goal.ethics_weight, 0.5), 4),
            confidence=round(confidence, 4),
            vicdan_alignment=vicdan_alignment,
            rationale=rationale,
        )

    def _recommended_actions(self, goal: CivilizationGoal) -> list[str]:
        base = {
            "food": [
                "Map underserved regions",
                "Launch local nutrition distribution pilots",
                "Pair food response with local production support",
            ],
            "health": [
                "Prioritize preventive screening access",
                "Deploy community health routing",
                "Measure early outcome improvement",
            ],
            "education": [
                "Identify high-need learners",
                "Deploy adaptive learning support",
                "Track retention and literacy gains",
            ],
            "energy": [
                "Stabilize local energy bottlenecks",
                "Prioritize efficient distributed generation",
                "Track cost and resilience improvements",
            ],
            "governance": [
                "Define transparent decision metrics",
                "Establish auditable contribution records",
                "Run trust-based feedback loops",
            ],
            "ai": [
                "Deploy guarded orchestration",
                "Measure answer reliability and harms prevented",
                "Increase traceability and policy enforcement",
            ],
        }
        return base.get(
            goal.category,
            [
                "Scope target population",
                "Run constrained pilot",
                "Measure impact and iterate",
            ],
        )

    def _required_resources(self, goal: CivilizationGoal) -> dict[str, Any]:
        return {
            "budget_estimate": round(10000 * (1.2 - goal.resource_efficiency), 2),
            "team_estimate": max(2, int(2 + (1.0 - goal.feasibility_score) * 8)),
            "time_estimate_months": {
                "immediate": 1,
                "short": 3,
                "medium": 6,
                "long": 12,
            }[goal.horizon],
            "critical_dependencies": goal.dependencies,
        }

    def prioritize(self, goals: list[CivilizationGoal]) -> PlanningOutput:
        accepted: list[tuple[CivilizationGoal, GoalScore]] = []
        deferred: list[GoalScore] = []

        for goal in goals:
            vicdan_status, reasons = VicdanGuard.evaluate_goal(goal, self.constraints)
            score = self.score_goal(goal)

            if vicdan_status == "REJECT":
                score.penalties.extend(reasons)
                deferred.append(score)
                continue

            if vicdan_status == "REVIEW":
                score.notes.extend(reasons)

            accepted.append((goal, score))

        accepted.sort(key=lambda x: x[1].final_score, reverse=True)
        selected = accepted[: self.constraints.max_parallel_goals]
        deferred.extend(score for _, score in accepted[self.constraints.max_parallel_goals :])

        decisions = [
            self.build_decision(goal, score, rank=i + 1)
            for i, (goal, score) in enumerate(selected)
        ]

        summary = self._build_summary(decisions, deferred)

        return PlanningOutput(
            top_goals=[score for _, score in selected],
            decisions=decisions,
            deferred_goals=deferred,
            planner_summary=summary,
        )

    def _build_summary(self, decisions: list[ResourceDecision], deferred: list[GoalScore]) -> str:
        if not decisions:
            return "No goals selected. Constraints or ethics filters blocked all candidates."

        top_names = ", ".join(d.goal_name for d in decisions)
        return (
            f"Selected {len(decisions)} priority goals: {top_names}. "
            f"Deferred {len(deferred)} additional goals for later phases or stronger resource readiness."
        )


def demo_goals() -> list[CivilizationGoal]:
    return [
        CivilizationGoal(
            id="goal_food_001",
            name="Child Nutrition Access",
            category="food",
            description="Reduce child hunger through targeted nutrition routing and local support.",
            urgency=0.95,
            impact_score=0.96,
            ethics_weight=1.00,
            feasibility_score=0.82,
            resource_efficiency=0.76,
            time_sensitivity=0.95,
            horizon="immediate",
            beneficiaries=250000,
            dependencies=["local_warehousing", "school_networks"],
            risks=[],
        ),
        CivilizationGoal(
            id="goal_edu_001",
            name="Adaptive Learning Access",
            category="education",
            description="Deliver adaptive education support to underserved learners.",
            urgency=0.82,
            impact_score=0.90,
            ethics_weight=0.97,
            feasibility_score=0.79,
            resource_efficiency=0.80,
            time_sensitivity=0.78,
            horizon="short",
            beneficiaries=180000,
            dependencies=["device_access", "teacher_enablement"],
            risks=[],
        ),
        CivilizationGoal(
            id="goal_energy_001",
            name="Distributed Energy Resilience",
            category="energy",
            description="Improve local energy reliability for vulnerable communities.",
            urgency=0.76,
            impact_score=0.91,
            ethics_weight=0.88,
            feasibility_score=0.68,
            resource_efficiency=0.61,
            time_sensitivity=0.74,
            horizon="medium",
            beneficiaries=120000,
            dependencies=["microgrid_partners", "maintenance_network"],
            risks=["ecological_damage"],
        ),
        CivilizationGoal(
            id="goal_ai_001",
            name="Trusted AI Public Service Layer",
            category="ai",
            description="Deploy traceable and governed AI assistance for public-impact workflows.",
            urgency=0.72,
            impact_score=0.84,
            ethics_weight=0.93,
            feasibility_score=0.86,
            resource_efficiency=0.83,
            time_sensitivity=0.66,
            horizon="short",
            beneficiaries=300000,
            dependencies=["policy_framework", "audit_logging"],
            risks=[],
        ),
    ]


if __name__ == "__main__":
    resources = SystemResources(
        budget=500000,
        people=40,
        energy_capacity=70,
        infrastructure_readiness=0.78,
        data_readiness=0.74,
        local_partnership_strength=0.81,
        time_budget_months=12,
    )

    ethics = EthicsProfile(
        protect_children_weight=1.0,
        reduce_suffering_weight=1.0,
        dignity_weight=0.95,
        sustainability_weight=0.90,
        fairness_weight=0.92,
        long_term_weight=0.88,
    )

    constraints = ConstraintSet(
        forbidden_categories=[],
        max_parallel_goals=3,
        min_ethics_threshold=0.55,
        prefer_fast_impact=True,
        require_local_readiness=False,
    )

    planner = HOPECorePlanner(resources=resources, ethics=ethics, constraints=constraints)
    output = planner.prioritize(demo_goals())

    print(json.dumps({
        "top_goals": [asdict(x) for x in output.top_goals],
        "decisions": [asdict(x) for x in output.decisions],
        "deferred_goals": [asdict(x) for x in output.deferred_goals],
        "planner_summary": output.planner_summary,
    }, indent=2))
