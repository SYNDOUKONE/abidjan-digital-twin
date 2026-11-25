"""Static configuration read from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("ADT_DATA_DIR", BASE_DIR / "data" / "processed"))
MODEL_DIR = Path(os.getenv("ADT_MODEL_DIR", BASE_DIR / "ai" / "traffic" / "models"))
SUMO_SCENARIOS_ROOT = Path(os.getenv("ADT_SCENARIOS_ROOT", BASE_DIR / "simulation" / "sumo" / "scenarios"))
SUMO_NET_FILE = Path(os.getenv("ADT_SUMO_NET", BASE_DIR / "simulation" / "sumo" / "abidjan_pilot" / "network" / "abidjan_pilot.net.xml"))
SUMO_ROUTES_FILE = Path(os.getenv("ADT_SUMO_ROUTES", BASE_DIR / "simulation" / "sumo" / "abidjan_pilot" / "demand" / "vehicles.rou.xml"))
SUMO_BIN = os.getenv("ADT_SUMO_BIN", "sumo")
MODEL_VERSION = "traffic-xgb-v1"
SNAPSHOT_INTERVAL_S = float(os.getenv("ADT_SNAPSHOT_INTERVAL_S", "1.0"))
DATA_MODE_LIVE = "simulated"
CITY = {
    "name": "Abidjan",
    "district": "District autonome d'Abidjan",
    "pilot_zone": "Le Plateau",
    "wgs84_center": {"latitude": 5.3217, "longitude": -4.0206},
}
