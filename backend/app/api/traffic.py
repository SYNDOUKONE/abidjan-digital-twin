from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from ..schemas import EdgeMetric, TrafficSnapshot, VehiclePosition
from ..services.simulation_manager import SimulationManager
from ..services.traffic_store import get_store

router = APIRouter(prefix="/api/v1/traffic", tags=["traffic"])


def get_manager() -> SimulationManager:
    from ..main import manager

    return manager


@router.get("/status")
def traffic_status() -> dict:
    snapshot = get_manager().active_snapshot()
    if snapshot is None:
        store = get_store()
        return {
            "status": "no_live_simulation",
            "data_mode": "simulated",
            "hint": "POST /api/v1/simulations to start a live SUMO simulation",
            "offline_scenarios": store.scenarios,
        }
    return {
        "status": "running",
        "simulation_id": snapshot["simulation_id"],
        "simulation_time": snapshot["simulation_time"],
        "vehicle_count": snapshot["vehicle_count"],
        "data_mode": "simulated",
    }


@router.get("/edges", response_model=list[EdgeMetric])
def traffic_edges(
    scenario: str = "baseline",
    time: float | None = None,
    congestion_level: str | None = None,
    limit: int = 500,
) -> list[EdgeMetric]:
    store = get_store()
    if scenario not in store.scenarios:
        raise HTTPException(status_code=404, detail=f"Unknown scenario '{scenario}'")
    if congestion_level and congestion_level not in ("free", "moderate", "high"):
        raise HTTPException(status_code=400, detail="congestion_level must be free|moderate|high")
    return [EdgeMetric(**row) for row in store.edge_metrics(scenario, time, congestion_level, limit)]


@router.get("/vehicles", response_model=list[VehiclePosition])
def traffic_vehicles(simulation_id: str | None = None) -> list[VehiclePosition]:
    manager = get_manager()
    snapshot = manager.latest_snapshot(simulation_id) if simulation_id else manager.active_snapshot()
    if snapshot is None:
        return []
    return [VehiclePosition(**v) for v in snapshot["vehicles"]]


@router.websocket("/stream")
async def traffic_stream(websocket: WebSocket, simulation_id: str | None = None) -> None:
    manager = get_manager()
    store = get_store()
    await websocket.accept()
    try:
        while True:
            snapshot = manager.latest_snapshot(simulation_id) if simulation_id else manager.active_snapshot()
            if snapshot is not None:
                payload = TrafficSnapshot(
                    simulation_id=snapshot["simulation_id"],
                    simulation_time=snapshot["simulation_time"],
                    data_mode="simulated",
                    vehicle_count=snapshot["vehicle_count"],
                    vehicles=[VehiclePosition(**v) for v in snapshot["vehicles"]],
                    edge_metrics=[EdgeMetric(**m) for m in snapshot["edge_metrics"]],
                )
                await websocket.send_json(payload.model_dump())
            else:
                await websocket.send_json({
                    "status": "no_live_simulation",
                    "data_mode": "simulated",
                    "offline_scenarios": store.scenarios,
                })
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return
