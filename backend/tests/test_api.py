from __future__ import annotations

import pandas as pd
from urllib.parse import quote


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["data_mode"] == "simulated"


def test_city_overview(client, baseline_frame: pd.DataFrame):
    response = client.get("/api/v1/city/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["district"]["name"] == "Abidjan"
    assert "baseline" in body["scenarios"]
    assert body["monitored_edges"] == baseline_frame["edge_id"].nunique()
    assert body["data_mode"] == "simulated"


def test_traffic_edges_returns_metrics(client):
    response = client.get("/api/v1/traffic/edges?scenario=baseline&limit=50")
    assert response.status_code == 200
    edges = response.json()
    assert 0 < len(edges) <= 50
    edge = edges[0]
    for field in ("edge_id", "mean_speed_kmh", "vehicle_count", "congestion_level", "data_mode"):
        assert field in edge
    assert edge["data_mode"] == "simulated"
    assert edge["congestion_level"] in ("free", "moderate", "high")


def test_traffic_edges_unknown_scenario(client):
    response = client.get("/api/v1/traffic/edges?scenario=does_not_exist")
    assert response.status_code == 404


def test_traffic_edges_filters_congestion(client):
    response = client.get("/api/v1/traffic/edges?scenario=baseline&congestion_level=high&limit=10")
    assert response.status_code == 200
    for edge in response.json():
        assert edge["congestion_level"] == "high"


def test_traffic_vehicles_empty_without_live_simulation(client):
    response = client.get("/api/v1/traffic/vehicles")
    assert response.status_code == 200
    assert response.json() == []


def test_create_and_list_scenarios(client):
    create = client.post(
        "/api/v1/scenarios",
        json={
            "name": "Fermeture du boulevard Lagunaire",
            "base_scenario": "road_closure",
            "closed_edge_ids": ["1165426094#0"],
            "description": "Scenario experimental de demonstration",
        },
    )
    assert create.status_code == 201
    created = create.json()
    assert created["name"].startswith("Fermeture")
    assert created["data_mode"] == "simulated"

    listed = client.get("/api/v1/scenarios")
    assert listed.status_code == 200
    scenario_ids = [s["scenario_id"] for s in listed.json()]
    assert created["scenario_id"] in scenario_ids
    assert "baseline" in scenario_ids


def test_prediction_endpoint(client, baseline_frame: pd.DataFrame):
    edge_id = baseline_frame["edge_id"].iloc[0]
    response = client.get(f"/api/v1/predictions/traffic?edge_id={quote(edge_id)}&scenario=baseline")
    assert response.status_code == 200
    body = response.json()
    assert body["edge_id"] == edge_id
    assert body["prediction_horizon_minutes"] == 15
    assert body["data_mode"] == "predicted"
    assert body["predicted_speed_kmh"] >= 0.0
    assert body["predicted_congestion"] in ("free", "moderate", "high")
    assert body["model_version"]


def test_prediction_unknown_edge(client):
    response = client.get("/api/v1/predictions/traffic?edge_id=nope&scenario=baseline")
    assert response.status_code == 404


def test_simulation_start_guard_when_sumo_missing(client, monkeypatch):
    from backend.app.main import manager

    monkeypatch.setattr(manager, "sumo_available", lambda: False)
    response = client.post("/api/v1/simulations", json={"scenario": "baseline", "duration_s": 60})
    assert response.status_code == 503
