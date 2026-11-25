"""Convert SUMO edge_data.xml outputs into tidy Parquet datasets.

Reads the edge_data.xml produced for each scenario, joins free-flow speeds from
the SUMO network, computes a congestion level per (edge, period) record and
writes one Parquet file per scenario plus a merged file.

Every row carries:
  scenario_id, simulation_time_s, edge_id, mean_speed_kmh, mean_speed_m_s,
  vehicle_count, occupancy_pct, free_flow_speed_kmh, speed_ratio,
  congestion_level, source, data_mode

Usage:
  python simulation/sumo/scripts/export_metrics.py \
      --net simulation/sumo/abidjan_pilot/network/abidjan_pilot.net.xml \
      --scenarios-root simulation/sumo/scenarios \
      --out data/processed
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import sumolib

MS_TO_KMH = 3.6


def classify_congestion(speed_ratio: float) -> str:
    if speed_ratio >= 0.7:
        return "free"
    if speed_ratio >= 0.4:
        return "moderate"
    return "high"


def parse_edge_data(path: Path) -> list[dict]:
    records: list[dict] = []
    root = ET.parse(path).getroot()
    interval: ET.Element
    for interval in root.iter("interval"):
        t_begin = float(interval.attrib["begin"])
        t_end = float(interval.attrib["end"])
        count = 0
        for edge in interval.findall("edge"):
            attrs = edge.attrib
            speed = float(attrs.get("speed", 0.0))
            occupancy = float(attrs.get("occupancy", 0.0))
            vehicles = int(attrs.get("departed", 0)) + int(attrs.get("left", 0))
            records.append({
                "simulation_time_s": t_end,
                "interval_begin_s": t_begin,
                "interval_end_s": t_end,
                "edge_id": attrs["id"],
                "mean_speed_m_s": speed,
                "mean_speed_kmh": round(speed * MS_TO_KMH, 2),
                "occupancy_pct": round(occupancy, 3),
                "vehicle_count": vehicles,
                "sampled_vehicle_seconds": round(float(attrs.get("sampledSeconds", 0.0)), 1),
            })
    return records


def parse_tripinfo_count(path: Path) -> int:
    root = ET.parse(path).getroot()
    return len(root.findall("tripinfo"))


def convert(net: Path, scenarios_root: Path, out_dir: Path) -> None:
    parsed_net = sumolib.net.readNet(str(net))
    free_flow = {
        edge.getID(): edge.getSpeed() * MS_TO_KMH
        for edge in parsed_net.getEdges()
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()

    frames: list[pd.DataFrame] = []
    for scenario_dir in sorted(p for p in scenarios_root.iterdir() if p.is_dir()):
        edge_data = scenario_dir / "edge_data.xml"
        tripinfo = scenario_dir / "tripinfo.xml"
        if not edge_data.exists():
            print(f"Skipping {scenario_dir}: no edge_data.xml")
            continue
        scenario_id = scenario_dir.name
        df = pd.DataFrame(parse_edge_data(edge_data))
        df["free_flow_speed_kmh"] = df["edge_id"].map(free_flow).round(1)
        df["speed_ratio"] = (df["mean_speed_kmh"] / df["free_flow_speed_kmh"]).round(3).fillna(0.0)
        df["congestion_level"] = df["speed_ratio"].apply(classify_congestion)
        df["scenario_id"] = scenario_id
        df["source"] = "sumo"
        df["data_mode"] = "simulated"
        df["generated_at_utc"] = generated_at
        out_path = out_dir / f"traffic_60s_{scenario_id}.parquet"
        df.to_parquet(out_path, index=False)
        n_trips = parse_tripinfo_count(tripinfo) if tripinfo.exists() else 0
        print(f"{scenario_id}: {len(df)} records / {df['edge_id'].nunique()} edges / {n_trips} trips -> {out_path}")
        frames.append(df)

    if frames:
        merged = pd.concat(frames, ignore_index=True)
        merged.to_parquet(out_dir / "traffic_60s_all.parquet", index=False)
        print(f"Merged dataset: {len(merged)} records -> {out_dir / 'traffic_60s_all.parquet'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export SUMO scenario metrics to Parquet")
    parser.add_argument("--net", type=Path, required=True)
    parser.add_argument("--scenarios-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    convert(args.net, args.scenarios_root, args.out)


if __name__ == "__main__":
    main()
