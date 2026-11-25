from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import config
from ..schemas import SimulationCreate, SimulationStatus
from ..services.simulation_manager import SimulationManager

router = APIRouter(prefix="/api/v1/simulations", tags=["simulations"])


def get_manager() -> SimulationManager:
    from ..main import manager

    return manager


@router.post("", status_code=202)
def start_simulation(payload: SimulationCreate) -> SimulationStatus:
    manager = get_manager()
    if not manager.sumo_available():
        raise HTTPException(
            status_code=503,
            detail="SUMO binary not found. Set ADT_SUMO_BIN or install SUMO.",
        )
    simulation_id = manager.start(payload.scenario, payload.duration_s)
    return SimulationStatus(
        simulation_id=simulation_id,
        scenario=payload.scenario,
        status="queued",
        simulation_time=0.0,
        duration_s=payload.duration_s,
        vehicle_count=0,
        data_mode="simulated",
    )


@router.get("/{simulation_id}", response_model=SimulationStatus)
def get_simulation(simulation_id: str) -> SimulationStatus:
    state = get_manager().get(simulation_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Unknown simulation '{simulation_id}'")
    return SimulationStatus(
        simulation_id=state["simulation_id"],
        scenario=state["scenario"],
        status=state["status"],
        simulation_time=state["simulation_time"],
        duration_s=state["duration_s"],
        vehicle_count=state["vehicle_count"],
        data_mode="simulated",
        error=state.get("error"),
    )


@router.get("", response_model=list[SimulationStatus])
def list_simulations() -> list[SimulationStatus]:
    manager = get_manager()
    return [
        SimulationStatus(
            simulation_id=s["simulation_id"],
            scenario=s["scenario"],
            status=s["status"],
            simulation_time=s["simulation_time"],
            duration_s=s["duration_s"],
            vehicle_count=s["vehicle_count"],
            data_mode="simulated",
        )
        for s in [manager.get(sid) for sid in manager.simulation_ids()]
        if s is not None
    ]
