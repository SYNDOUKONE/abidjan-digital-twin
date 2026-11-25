from __future__ import annotations

import uuid

from fastapi import APIRouter

from ..schemas import ScenarioCreate, ScenarioDefinition
from ..services.scenario_registry import get_registry

router = APIRouter(prefix="/api/v1/scenarios", tags=["scenarios"])


@router.post("", status_code=201)
def create_scenario(payload: ScenarioCreate) -> ScenarioDefinition:
    scenario_id = f"scn_{uuid.uuid4().hex[:8]}"
    return get_registry().create(scenario_id, payload.model_dump())


@router.get("", response_model=list[ScenarioDefinition])
def list_scenarios() -> list[ScenarioDefinition]:
    return get_registry().list()
