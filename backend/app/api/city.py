from __future__ import annotations

from fastapi import APIRouter

from ..services.traffic_store import get_store

router = APIRouter(prefix="/api/v1/city", tags=["city"])


@router.get("/overview")
def city_overview() -> dict:
    return get_store().overview()
