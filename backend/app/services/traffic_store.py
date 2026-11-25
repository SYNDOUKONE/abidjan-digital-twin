"""Traffic data store backed by the Parquet exports of the simulation pipeline."""

from __future__ import annotations

import threading
from functools import lru_cache
from pathlib import Path

import pandas as pd

from .. import config


class TrafficStore:
    def __init__(self, data_dir: Path | None = None):
        self._data_dir = Path(data_dir) if data_dir else config.DATA_DIR
        self._lock = threading.Lock()
        self._frames: dict[str, pd.DataFrame] = {}
        self._reload()

    def _reload(self) -> None:
        frames: dict[str, pd.DataFrame] = {}
        if self._data_dir.exists():
            for path in sorted(self._data_dir.glob("traffic_60s_*.parquet")):
                if path.stem == "traffic_60s_all":
                    continue
                scenario_id = path.stem.replace("traffic_60s_", "")
                frames[scenario_id] = pd.read_parquet(path)
        with self._lock:
            self._frames = frames

    def reload(self) -> None:
        self._reload()

    @property
    def scenarios(self) -> list[str]:
        return sorted(self._frames.keys())

    def _base(self, scenario: str) -> pd.DataFrame | None:  # noqa: ANN001
        with self._lock:
            return self._frames.get(scenario)

    def overview(self) -> dict:
        with self._lock:
            frames = dict(self._frames)
        if not frames:
            return {"scenarios": [], "district": config.CITY}
        all_df = pd.concat(frames.values(), ignore_index=True)
        congestion = all_df["congestion_level"].value_counts().to_dict()
        return {
            "district": config.CITY,
            "scenarios": self.scenarios,
            "monitored_edges": int(all_df["edge_id"].nunique()),
            "records": int(len(all_df)),
            "simulation_time_window_s": [
                float(all_df["simulation_time_s"].min()),
                float(all_df["simulation_time_s"].max()),
            ],
            "congestion_distribution": congestion,
            "data_mode": "simulated",
        }

    def edge_metrics(
        self,
        scenario: str,
        simulation_time: float | None = None,
        congestion_level: str | None = None,
        limit: int = 500,
    ) -> list[dict]:
        df = self._base(scenario)
        if df is None:
            return []
        if simulation_time is None:
            simulation_time = df["simulation_time_s"].max()
        subset = df[df["simulation_time_s"] == simulation_time]
        if congestion_level:
            subset = subset[subset["congestion_level"] == congestion_level]
        subset = subset.sort_values("vehicle_count", ascending=False).head(limit)
        return [
            {
                "edge_id": row.edge_id,
                "mean_speed_kmh": row.mean_speed_kmh,
                "vehicle_count": int(row.vehicle_count),
                "occupancy_pct": row.occupancy_pct,
                "free_flow_speed_kmh": row.free_flow_speed_kmh,
                "speed_ratio": row.speed_ratio,
                "congestion_level": row.congestion_level,
                "data_mode": "simulated",
            }
            for row in subset.itertuples(index=False)
        ]

    def edge_state(self, scenario: str, edge_id: str) -> dict | None:
        df = self._base(scenario)
        if df is None or edge_id not in set(df["edge_id"].unique()):
            return None
        row = df[df["edge_id"] == edge_id].sort_values("simulation_time_s").iloc[-1]
        return {
            "edge_id": edge_id,
            "mean_speed_kmh": float(row.mean_speed_kmh),
            "vehicle_count": int(row.vehicle_count),
            "occupancy_pct": float(row.occupancy_pct),
            "speed_ratio": float(row.speed_ratio),
            "free_flow_speed_kmh": float(row.free_flow_speed_kmh),
            "congestion_level": row.congestion_level,
            "simulation_time_s": float(row.simulation_time_s),
        }

    def series(self, scenario: str, edge_id: str) -> list[dict]:
        df = self._base(scenario)
        if df is None or edge_id not in set(df["edge_id"].unique()):
            return []
        subset = df[df["edge_id"] == edge_id].sort_values("simulation_time_s")
        return [
            {
                "simulation_time_s": float(row.simulation_time_s),
                "mean_speed_kmh": float(row.mean_speed_kmh),
                "vehicle_count": int(row.vehicle_count),
                "congestion_level": row.congestion_level,
            }
            for row in subset.itertuples(index=False)
        ]


@lru_cache(maxsize=1)
def get_store() -> TrafficStore:
    return TrafficStore()
