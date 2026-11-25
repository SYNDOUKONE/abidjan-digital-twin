"""Traffic prediction service backed by the XGBoost model trained on SUMO data.

Falls back to a persistence (naive) baseline when the model artifact is not
present. All predictions carry data_mode="predicted".
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from .. import config

MODEL_FILE = "traffic-xgb-v1"
FEATURE_COUNT = 8


class PredictionService:
    def __init__(self, model_dir: Path | None = None):
        self._model_dir = Path(model_dir) if model_dir else config.MODEL_DIR
        self._lock = threading.Lock()
        self._model = None
        self._version = "naive-persistence-v1"
        self._load_model()

    def _load_model(self) -> None:
        model_path = self._model_dir / f"{MODEL_FILE}.json"
        meta_path = self._model_dir / f"{MODEL_FILE}.meta.json"
        if not model_path.exists():
            return
        try:
            import xgboost as xgb

            model = xgb.XGBRegressor()
            model.load_model(model_path)
            with self._lock:
                self._model = model
                if meta_path.exists():
                    self._version = json.loads(meta_path.read_text(encoding="utf-8")).get(
                        "version", self._version
                    )
                else:
                    self._version = MODEL_FILE
        except Exception as error:  # noqa: BLE001
            print(f"[prediction] Failed to load model: {error}")

    @property
    def model_version(self) -> str:
        with self._lock:
            return self._version

    @property
    def model_loaded(self) -> bool:
        with self._lock:
            return self._model is not None

    def predict_next(self, state: dict) -> dict:
        """Predict the mean speed 15 minutes ahead for one edge."""
        mean_speed = float(state["mean_speed_kmh"])
        if self._model is None:
            predicted_speed = round(mean_speed, 1)
        else:
            ratio_t = min(1.0, mean_speed / max(float(state["free_flow_speed_kmh"]), 1.0))
            features = [[
                mean_speed,
                ratio_t,
                float(state["vehicle_count"]),
                float(state["occupancy_pct"]),
                float(state["free_flow_speed_kmh"]),
                mean_speed,
                mean_speed,
                mean_speed,
            ]]
            predicted_speed = round(float(self._model.predict(features)[0]), 1)

        ratio = predicted_speed / max(float(state["free_flow_speed_kmh"]), 1.0)
        if ratio >= 0.7:
            congestion = "free"
        elif ratio >= 0.4:
            congestion = "moderate"
        else:
            congestion = "high"
        return {
            "edge_id": state["edge_id"],
            "prediction_horizon_minutes": 15,
            "predicted_speed_kmh": predicted_speed,
            "predicted_congestion": congestion,
            "data_mode": "predicted",
            "model_version": self.model_version,
        }
