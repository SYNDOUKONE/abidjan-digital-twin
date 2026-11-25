from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas import PredictionResponse
from ..services.prediction_service import PredictionService
from ..services.traffic_store import get_store

router = APIRouter(prefix="/api/v1/predictions", tags=["predictions"])

_service: PredictionService | None = None


def get_service() -> PredictionService:
    global _service
    if _service is None:
        _service = PredictionService()
    return _service


@router.get("/traffic", response_model=PredictionResponse)
def predict_traffic(edge_id: str, scenario: str = "baseline") -> PredictionResponse:
    store = get_store()
    if scenario not in store.scenarios:
        raise HTTPException(status_code=404, detail=f"Unknown scenario '{scenario}'")
    state = store.edge_state(scenario, edge_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Unknown edge '{edge_id}'")
    prediction = get_service().predict_next(state)
    return PredictionResponse(**prediction)


@router.get("/model")
def model_info() -> dict:
    service = get_service()
    return {
        "model_version": service.model_version,
        "model_loaded": service.model_loaded,
        "horizon_minutes": 15,
        "trained_on": "simulated SUMO scenarios (data_mode=simulated)",
        "caution": "Predictions are experimental until validated on real observations.",
    }
