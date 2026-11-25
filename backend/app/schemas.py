"""Pydantic schemas shared by the API routers."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Congestion = Literal["free", "moderate", "high"]


class HealthResponse(BaseModel):
    status: str
    data_mode: str
    version: str = "v1"


class EdgeMetric(BaseModel):
    edge_id: str
    mean_speed_kmh: float
    vehicle_count: int
    occupancy_pct: float
    free_flow_speed_kmh: float
    speed_ratio: float
    congestion_level: Congestion
    data_mode: str = "simulated"


class VehiclePosition(BaseModel):
    vehicle_id: str
    edge_id: str | None = None
    longitude: float
    latitude: float
    heading_deg: float
    speed_kmh: float
    simulation_time: float
    data_mode: str = "simulated"


class TrafficSnapshot(BaseModel):
    simulation_id: str
    simulation_time: float
    data_mode: str
    vehicle_count: int
    vehicles: list[VehiclePosition]
    edge_metrics: list[EdgeMetric]


class SimulationCreate(BaseModel):
    scenario: Literal["baseline", "high_demand", "road_closure", "accident", "rain"] = "baseline"
    duration_s: int = Field(default=600, ge=30, le=3600)


class SimulationStatus(BaseModel):
    simulation_id: str
    scenario: str
    status: Literal["queued", "running", "completed", "failed"]
    simulation_time: float
    duration_s: int
    vehicle_count: int
    data_mode: str
    error: str | None = None


class ScenarioCreate(BaseModel):
    name: str = Field(min_length=3, max_length=64)
    base_scenario: Literal["baseline", "high_demand", "road_closure", "accident", "rain"] = "baseline"
    closed_edge_ids: list[str] = []
    demand_scale: float = Field(default=1.0, ge=0.1, le=10.0)
    description: str | None = None


class ScenarioDefinition(BaseModel):
    scenario_id: str
    name: str
    base_scenario: str
    closed_edge_ids: list[str]
    demand_scale: float
    description: str | None
    data_mode: str = "simulated"


class PredictionRequest(BaseModel):
    edge_id: str
    scenario: str = "baseline"
    horizon_minutes: int = Field(default=15, ge=1, le=60)


class PredictionResponse(BaseModel):
    edge_id: str
    prediction_horizon_minutes: int
    predicted_speed_kmh: float
    predicted_congestion: Congestion
    data_mode: str = "predicted"
    model_version: str
