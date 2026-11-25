"""In-memory registry of scenario definitions created through the API."""

from __future__ import annotations

import threading

from ..schemas import ScenarioDefinition

BUILT_IN_SCENARIOS = ["baseline", "high_demand", "road_closure", "accident", "rain"]


class ScenarioRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._scenarios: dict[str, ScenarioDefinition] = {
            scenario_id: ScenarioDefinition(
                scenario_id=scenario_id,
                name=f"SUMO {scenario_id} scenario",
                base_scenario=scenario_id,
                closed_edge_ids=[],
                demand_scale=1.2 if scenario_id == "high_demand" else 1.0,
                description=None,
            )
            for scenario_id in BUILT_IN_SCENARIOS
        }

    def create(self, scenario_id: str, payload: dict) -> ScenarioDefinition:
        definition = ScenarioDefinition(
            scenario_id=scenario_id,
            name=payload["name"],
            base_scenario=payload["base_scenario"],
            closed_edge_ids=payload.get("closed_edge_ids", []),
            demand_scale=payload.get("demand_scale", 1.0),
            description=payload.get("description"),
        )
        with self._lock:
            self._scenarios[scenario_id] = definition
        return definition

    def list(self) -> list[ScenarioDefinition]:
        with self._lock:
            return list(self._scenarios.values())

    def get(self, scenario_id: str) -> ScenarioDefinition | None:
        with self._lock:
            return self._scenarios.get(scenario_id)


_REGISTRY: ScenarioRegistry | None = None


def get_registry() -> ScenarioRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = ScenarioRegistry()
    return _REGISTRY
