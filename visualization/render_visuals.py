"""Render visual reports from the Milestone 1 pilot network.

Produces (in --outdir):
  - congestion_<scenario>.png : network map colored by 1-min mean speed ratio
  - scenario_comparison.png   : congestion share + vehicles by scenario
  - traffic_animation.gif     : live SUMO traffic replay over the network

Usage:
  python visualization/render_visuals.py \
      --net simulation/sumo/abidjan_pilot/network/abidjan_pilot.net.xml \
      --data-dir data/processed --outdir docs/visuals
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sumolib
from matplotlib.collections import LineCollection
from PIL import Image

COLORS = {"free": "#2ecc71", "moderate": "#f39c12", "high": "#e74c3c", "closed": "#7f8c8d"}
PANEL_DPI = 110
PNG_PATHS = {
    "baseline": "#2ecc71",
    "high_demand": "#9b59b6",
    "road_closure": "#e67e22",
    "accident": "#c0392b",
    "rain": "#3498db",
}


def edge_shapes_lonlat(net: sumolib.net.Net) -> dict[str, list[tuple[float, float]]]:
    shapes = {}
    for edge in net.getEdges():
        if edge.isSpecial() or edge.getFromNode() == edge.getToNode():
            continue
        shape = edge.getShape()
        lonlat = [net.convertXY2LonLat(x, y) for x, y in shape]
        shapes[edge.getID()] = lonlat
    return shapes


def draw_network(ax, shapes, speed_by_edge: dict[str, float] | None = None, alpha: float = 0.9):
    segments, colors = [], []
    for edge_id, shape in shapes.items():
        if speed_by_edge is None:
            color = "#b9c2c6"
        else:
            ratio = speed_by_edge.get(edge_id)
            if ratio is None:
                color = "#e5e8e8"
            elif ratio < 0.4:
                color = COLORS["high"]
            elif ratio < 0.7:
                color = COLORS["moderate"]
            else:
                color = COLORS["free"]
        segments.append(shape)
        colors.append(color)
    collection = LineCollection(segments, colors=colors, linewidths=0.9, alpha=alpha)
    ax.add_collection(collection)
    ax.autoscale()
    ax.set_aspect(1.0 / np.cos(np.deg2rad(5.32)))
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")


def congestion_maps(net, shapes, data_dir: Path, scenarios: list[str], outdir: Path):
    for scenario in scenarios:
        df = pd.read_parquet(data_dir / f"traffic_60s_{scenario}.parquet")
        last_t = df["simulation_time_s"].max()
        snapshot = df[df["simulation_time_s"] == last_t]
        speed_by_edge = dict(zip(snapshot["edge_id"], snapshot["speed_ratio"]))
        fig, ax = plt.subplots(figsize=(9, 9))
        draw_network(ax, shapes, speed_by_edge)
        ax.set_title(f"Abidjan — Le Plateau — réseau pilot\n{scenario} (minute {int(last_t) // 60})")
        handles = [
            plt.Line2D([0], [0], color=COLORS["free"], lw=3, label="fluide (ratio >= 0,7)"),
            plt.Line2D([0], [0], color=COLORS["moderate"], lw=3, label="dense (0,4-0,7)"),
            plt.Line2D([0], [0], color=COLORS["high"], lw=3, label="congestionné (< 0,4)"),
            plt.Line2D([0], [0], color="#e5e8e8", lw=1, label="sans trafic"),
        ]
        ax.legend(handles=handles, loc="lower left", fontsize=8)
        fig.tight_layout()
        path = outdir / f"congestion_{scenario}.png"
        fig.savefig(path, dpi=PANEL_DPI)
        plt.close(fig)
        print("wrote", path)


def scenario_comparison(data_dir: Path, scenarios: list[str], outdir: Path):
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    shares, vehicles, labels = [], [], []
    for scenario in scenarios:
        df = pd.read_parquet(data_dir / f"traffic_60s_{scenario}.parquet")
        shares.append((df["congestion_level"] != "free").mean() * 100)
        vehicles.append(int(df["vehicle_count"].sum()))
        labels.append(scenario)

    bar_colors = [PNG_PATHS.get(s, "#2ecc71") for s in labels]
    axes[0].bar(labels, shares, color=bar_colors)
    axes[0].set_title("Part des périodes denses/congestionnées")
    axes[0].set_ylabel("% des enregistrements edge-minute")
    axes[0].tick_params(axis="x", rotation=20)

    axes[1].bar(labels, vehicles, color=bar_colors)
    axes[1].set_title("Volumes de trafic cumulés (véhicules par segment-minute)")
    axes[1].tick_params(axis="x", rotation=20)

    fig.suptitle("Comparaison des scénarios SUMO — zone pilote Le Plateau (données simulées)")
    fig.tight_layout()
    path = outdir / "scenario_comparison.png"
    fig.savefig(path, dpi=PANEL_DPI)
    plt.close(fig)
    print("wrote", path)


def sample_trips_trajectories(
    net_path: Path,
    cfg: Path,
    frames: int,
    step_every: int,
    sumo_bin: str,
) -> list[dict[float, list[tuple[float, float]]]]:
    """Run SUMO via TraCI and sample vehicle positions (network coords) each step_every s."""
    import traci

    cmd = [sumo_bin, "-c", str(cfg), "--no-step-log", "--ignore-route-errors"]
    conn = None
    try:
        traci.start(cmd, label="viz")
        conn = traci.getConnection(label="viz")
        samples: list[dict[float, list[tuple[float, float]]]] = []
        sim_time = 0.0
        duration = frames * step_every
        while sim_time < duration and conn.simulation.getMinExpectedNumber() > 0:
            conn.simulationStep()
            sim_time = conn.simulation.getTime()
            if int(sim_time) % step_every != 0:
                continue
            positions = []
            for vehicle_id in conn.vehicle.getIDList():
                x, y = conn.vehicle.getPosition(vehicle_id)
                positions.append((x, y))
            samples.append({sim_time: positions})
        return samples
    finally:
        try:
            traci.close()
        except Exception:
            pass


def traffic_animation(net, shapes, cfg: Path, outdir: Path, sumo_bin: str,
                      frames: int = 60, step_every: int = 5):
    samples = sample_trips_trajectories(net, cfg, frames, step_every, sumo_bin)
    net_frames = []
    fig, ax = plt.subplots(figsize=(9, 9))
    for sample in samples:
        (sim_time, positions), = sample.items()
        draw_network(ax, shapes, alpha=0.55)
        if positions:
            xs, ys = zip(*positions)
            lonlat = [net.convertXY2LonLat(x, y) for x, y in zip(xs, ys)]
            ax.scatter([p[0] for p in lonlat], [p[1] for p in lonlat], s=14, color="#17202a", zorder=5)
        ax.set_title(f"Abidjan — Le Plateau — trafic simulé (t={int(sim_time)} s)")
        ax.set_xlabel("longitude")
        ax.set_ylabel("latitude")
        fig.tight_layout()
        temp_path = outdir / "_frame.png"
        fig.savefig(temp_path, dpi=PANEL_DPI)
        net_frames.append(Image.open(temp_path).convert("RGB").copy())
        ax.clear()
    plt.close(fig)
    temp_path.unlink(missing_ok=True)

    path = outdir / "traffic_animation.gif"
    if net_frames:
        net_frames[0].save(path, save_all=True, append_images=net_frames[1:], duration=180, loop=0)
        print(f"wrote {path} ({len(net_frames)} frames)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render pilot visual reports")
    parser.add_argument("--net", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--outdir", type=Path, default=Path("docs/visuals"))
    parser.add_argument("--baseline-cfg", type=Path,
                        default=Path("simulation/sumo/scenarios/baseline/scenario.sumocfg"))
    parser.add_argument("--scenarios", nargs="+",
                        default=["baseline", "high_demand", "road_closure", "accident", "rain"])
    parser.add_argument("--animation", action="store_true", help="also render the GIF")
    parser.add_argument("--animation-frames", type=int, default=60)
    parser.add_argument("--animation-step", type=int, default=5)
    parser.add_argument("--sumo-bin", default=os.environ.get("SUMO_BIN", "sumo"))
    args = parser.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)
    net = sumolib.net.readNet(str(args.net))
    shapes = edge_shapes_lonlat(net)

    congestion_maps(net, shapes, args.data_dir, args.scenarios, args.outdir)
    scenario_comparison(args.data_dir, args.scenarios, args.outdir)
    if args.animation:
        traffic_animation(net, shapes, args.baseline_cfg, args.outdir, args.sumo_bin,
                          args.animation_frames, args.animation_step)


if __name__ == "__main__":
    main()
