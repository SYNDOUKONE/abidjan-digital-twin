"""FastAPI application entrypoint for the Abidjan Digital Twin backend."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .api import city, predictions, scenarios, simulations, traffic
from .schemas import HealthResponse
from .services.simulation_manager import SimulationManager

manager = SimulationManager()

app = FastAPI(
    title="Abidjan Digital Twin API",
    version="0.1.0",
    description=(
        "Backend for the Abidjan Digital Twin: traffic indicators from SUMO "
        "simulations (data_mode=simulated), scenario management and XGBoost "
        "traffic predictions (data_mode=predicted)."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(city.router)
app.include_router(traffic.router)
app.include_router(simulations.router)
app.include_router(scenarios.router)
app.include_router(predictions.router)


@app.get("/health", tags=["health"], response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", data_mode="simulated")
