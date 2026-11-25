"""Train the XGBoost speed predictor on SUMO scenario data.

Task: predict the mean speed of an edge 15 minutes ahead, given the current
traffic state. This model is trained on SIMULATED data (data_mode="simulated")
from the SUMO scenarios; it does not prove good predictions on real Abidjan
traffic until real observations are integrated and used for validation.

Outputs:
  ai/traffic/models/traffic_xgb_v1.json      - trained model
  ai/traffic/models/traffic_xgb_v1.meta.json - feature list + training metadata
  ai/traffic/evaluation/xgb_metrics.json     - MAE / RMSE vs naive baseline

Usage:
  python ai/traffic/src/train_xgboost.py \
      --dataset data/processed/traffic_60s_all.parquet \
      --net simulation/sumo/abidjan_pilot/network/abidjan_pilot.net.xml
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

HORIZON_MINUTES = 15
PERIOD_S = 60
LAG_STEPS = HORIZON_MINUTES * 60 // PERIOD_S
FEATURE_COLUMNS = [
    "mean_speed_t",
    "speed_ratio_t",
    "vehicle_count_t",
    "occupancy_t",
    "free_flow_speed_kmh",
    "traffic_state_past_1",
    "traffic_state_past_3",
    "traffic_state_past_5",
]


def build_features(df: pd.DataFrame, lane_count: dict[str, int]) -> pd.DataFrame:
    df = df.sort_values(["edge_id", "simulation_time_s"]).copy()
    df["lanes"] = df["edge_id"].map(lane_count).fillna(1)
    df["mean_speed_t"] = df["mean_speed_kmh"]
    df["speed_ratio_t"] = df["speed_ratio"]
    df["vehicle_count_t"] = df["vehicle_count"]
    df["occupancy_t"] = df["occupancy_pct"]

    grouped = df.groupby("edge_id", sort=False)
    df["target_speed_t_plus_15"] = grouped["mean_speed_kmh"].shift(-LAG_STEPS)
    df["traffic_state_past_1"] = grouped["mean_speed_kmh"].shift(1)
    df["traffic_state_past_3"] = grouped["mean_speed_kmh"].shift(3).fillna(df["mean_speed_t"])
    df["traffic_state_past_5"] = grouped["mean_speed_kmh"].shift(5).fillna(df["mean_speed_t"])
    df = df.dropna(subset=["target_speed_t_plus_15"])
    return df


def chrono_split(df: pd.DataFrame, train: float = 0.7, val: float = 0.15) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split by simulation time so the model only sees the past."""
    times = sorted(df["simulation_time_s"].unique())
    train_end = times[int(len(times) * train)]
    val_end = times[int(len(times) * (train + val))]
    train_df = df[df["simulation_time_s"] <= train_end]
    val_df = df[(df["simulation_time_s"] > train_end) & (df["simulation_time_s"] <= val_end)]
    test_df = df[df["simulation_time_s"] > val_end]
    return train_df, val_df, test_df


def metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    diff = y_true - y_pred
    return {
        "mae": round(float(np.mean(np.abs(diff))), 3),
        "rmse": round(float(np.sqrt(np.mean(diff**2))), 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the XGBoost speed predictor")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--net", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, default=Path("ai/traffic/models"))
    parser.add_argument("--eval-dir", type=Path, default=Path("ai/traffic/evaluation"))
    args = parser.parse_args()

    import sumolib

    parsed = sumolib.net.readNet(str(args.net))
    lane_count = {e.getID(): e.getLaneNumber() for e in parsed.getEdges()}

    raw = pd.read_parquet(args.dataset)
    df = build_features(raw, lane_count)
    train_df, val_df, test_df = chrono_split(df)
    print(f"Samples: train={len(train_df)} validation={len(val_df)} test={len(test_df)}")

    X_cols = FEATURE_COLUMNS
    X_train = train_df[X_cols].to_numpy()
    y_train = train_df["target_speed_t_plus_15"].to_numpy()
    X_val = val_df[X_cols].to_numpy()
    y_val = val_df["target_speed_t_plus_15"].to_numpy()
    X_test = test_df[X_cols].to_numpy()
    y_test = test_df["target_speed_t_plus_15"].to_numpy()

    model = xgb.XGBRegressor(
        n_estimators=400,
        max_depth=8,
        learning_rate=0.08,
        subsample=0.8,
        colsample_bytree=0.8,
        tree_method="hist",
        objective="reg:squarederror",
        early_stopping_rounds=25,
        n_jobs=4,
    )
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

    pred = model.predict(X_test)
    xgb_scores = metrics(y_test, pred)

    naive_pred = test_df["mean_speed_t"].to_numpy()
    baseline_scores = metrics(y_test, naive_pred)

    print(f"XGBoost  MAE={xgb_scores['mae']} RMSE={xgb_scores['rmse']}")
    print(f"Baseline MAE={baseline_scores['mae']} RMSE={baseline_scores['rmse']}")
    improvement = round(
        100 * (baseline_scores["mae"] - xgb_scores["mae"]) / baseline_scores["mae"], 1
    ) if baseline_scores["mae"] else 0.0
    print(f"MAE improvement vs naive baseline: {improvement}%")

    version = "traffic-xgb-v1"
    model_path = args.model_dir / f"{version}.json"
    meta_path = args.model_dir / f"{version}.meta.json"
    metrics_path = args.eval_dir / f"{version}_metrics.json"

    args.model_dir.mkdir(parents=True, exist_ok=True)
    args.eval_dir.mkdir(parents=True, exist_ok=True)
    model.save_model(model_path)
    meta_path.write_text(
        json.dumps({
            "version": version,
            "feature_columns": X_cols,
            "horizon_minutes": HORIZON_MINUTES,
            "trained_at_utc": datetime.now(timezone.utc).isoformat(),
            "n_features": len(X_cols),
            "booster_best_iteration": int(model.best_iteration or model.n_estimators),
        }, indent=2),
        encoding="utf-8",
    )
    metrics_path.write_text(
        json.dumps({
            "version": version,
            "dataset": str(args.dataset),
            "n_train": len(train_df),
            "n_validation": len(val_df),
            "n_test": len(test_df),
            "xgboost": xgb_scores,
            "naive_baseline": baseline_scores,
            "mae_improvement_percent": improvement,
            "note": "Trained and evaluated on SIMULATED SUMO data only.",
            "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        }, indent=2),
        encoding="utf-8",
    )
    print(f"Model saved: {model_path}")
    print(f"Metrics saved: {metrics_path}")


if __name__ == "__main__":
    main()
