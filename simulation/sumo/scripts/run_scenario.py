"""Run a scenario (baseline, high_demand, road_closure, accident, rain) in SUMO.

Builds the additional files, the .sumocfg and the scenario directory, then runs
SUMO headlessly. Outputs (edge_data.xml, tripinfo.xml) go to the scenario output
directory.

Scenarios are experimental hypotheses on simulated demand, never measurements
of real Abidjan traffic. Every produced record carries data_mode="simulated".

Usage:
  python simulation/sumo/scripts/run_scenario.py --scenario baseline \
      --net simulation/sumo/abidjan_pilot/network/abidjan_pilot.net.xml \
      --routes simulation/sumo/abidjan_pilot/demand/vehicles.rou.xml \
      --begin 0 --end 3600 --period 60
"""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

import sumolib

SCENARIOS = ("baseline", "high_demand", "road_closure", "accident", "rain")


def pick_arterial_edges(net: sumolib.net.Net, count: int) -> list[str]:
    """Deterministically choose the most structurally important edges (main arteries)."""
    candidates = []
    for edge in net.getEdges():
        if edge.isSpecial():  # traffic lights, degenerate junctions
            continue
        if edge.getFromNode() == edge.getToNode():
            continue
        lanes = edge.getLaneNumber()
        speed = edge.getSpeed()
        length = edge.getLength()
        if lanes < 2 or speed < 13.9:  # roughly > 50 km/h roads only
            continue
        candidates.append((lanes * length * speed, edge.getID()))
    candidates.sort(reverse=True)
    return [edge_id for _, edge_id in candidates[:count]]


def build_closure_additional(edge_ids: list[str], lanes_blocked: int, path: Path) -> None:
    """Close edges via rerouter closingReroute (whole edge for all lanes when
    lanes_blocked >= 2, otherwise a single lane via closingLaneReroute)."""
    lines = ['<additional>']
    edge_attrs = " ".join(edge_ids)
    lines.append(f'    <rerouter id="closure_rr" edges="{edge_attrs}">')
    lines.append('        <interval begin="0" end="999999">')
    if lanes_blocked >= 2:
        for edge_id in edge_ids:
            lines.append(f'            <closingReroute id="{edge_id}" disallow="all"/>')
    else:
        for edge_id in edge_ids:
            lines.append(f'            <closingLaneReroute id="{edge_id}_0" disallow="all"/>')
    lines.append('        </interval>')
    lines.append('    </rerouter>')
    lines.append('</additional>')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_rain_vss(net: sumolib.net.Net, edge_ids: list[str], speed_factor: float, path: Path) -> None:
    lines = ['<additional>']
    for edge_id in edge_ids:
        lane_ids = [lane.getID() for lane in net.getEdge(edge_id).getLanes()]
        new_speed = round(net.getEdge(edge_id).getSpeed() * speed_factor, 2)
        lines.append(f'    <variableSpeedSign id="vss_{edge_id}" lanes="{" ".join(lane_ids)}">')
        lines.append(f'        <step time="0" speed="{new_speed}"/>')
        lines.append('    </variableSpeedSign>')
    lines.append('</additional>')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_edge_data_additional(path: Path, period: int) -> None:
    path.write_text(
        '<additional>\n'
        f'    <edgeData id="scenario_metrics" file="edge_data.xml" period="{period}" '
        'excludeEmpty="true"/>\n'
        '</additional>\n',
        encoding="utf-8",
    )


def build_sumocfg(net: Path, routes: Path, additional: str, end: int, outdir: Path,
                  demand_scale: float | None) -> Path:
    cfg_lines = [
        '<configuration>',
        '    <input>',
        f'        <net-file value="{net.name}"/>',
        f'        <route-files value="{routes.name}"/>',
        f'        <additional-files value="{additional}"/>',
        '    </input>',
        '    <output>',
        '        <tripinfo-output value="tripinfo.xml"/>',
        '    </output>',
        '    <time>',
        f'        <begin value="0"/>',
        f'        <end value="{end}"/>',
        '    </time>',
    ]
    if demand_scale and demand_scale != 1.0:
        cfg_lines += ['    <processing>', f'        <scale value="{demand_scale}"/>', '    </processing>']
    cfg_lines.append('</configuration>')
    cfg_path = outdir / "scenario.sumocfg"
    # net lives in the shared network dir; point config inputs at absolute parents via param files
    if net.parent.resolve() != outdir.resolve():
        cfg_lines = [line.replace(f'value="{net.name}"', f'value="{net.resolve()}"')
                     .replace(f'value="{routes.name}"', f'value="{routes.resolve()}"')
                     for line in cfg_lines]
    cfg_path.write_text("\n".join(cfg_lines) + "\n", encoding="utf-8")
    return cfg_path


SCENARIO_SETTINGS = {
    "baseline":     {"demand_scale": None, "closed_edges": 0, "blocked_lanes": 0, "rain": False},
    "high_demand":  {"demand_scale": 1.2, "closed_edges": 0, "blocked_lanes": 0, "rain": False},
    "road_closure": {"demand_scale": None, "closed_edges": 1, "blocked_lanes": 99, "rain": False},
    "accident":     {"demand_scale": None, "closed_edges": 1, "blocked_lanes": 1, "rain": False},
    "rain":         {"demand_scale": None, "closed_edges": 0, "blocked_lanes": 0, "rain": True},
}


def prepare_scenario(scenario: str, net: Path, routes: Path, scenarios_root: Path,
                     end: int, period: int, arterial_count: int) -> tuple[Path, Path]:
    settings = SCENARIO_SETTINGS[scenario]
    outdir = scenarios_root / scenario
    outdir.mkdir(parents=True, exist_ok=True)
    build_edge_data_additional(outdir / "metrics.add.xml", period)

    additional_files = "metrics.add.xml"
    if settings["closed_edges"]:
        parsed = sumolib.net.readNet(str(net))
        edges = pick_arterial_edges(parsed, settings["closed_edges"])
        if not edges:
            raise SystemExit("No arterial edge found to close")
        build_closure_additional(edges, settings["blocked_lanes"], outdir / "closure.add.xml")
        additional_files += ",closure.add.xml"
        print(f"Scenario '{scenario}': closing {edges}")
    if settings["rain"]:
        parsed = sumolib.net.readNet(str(net))
        edges = pick_arterial_edges(parsed, max(arterial_count, 5))
        build_rain_vss(parsed, edges, 0.7, outdir / "rain_vss.add.xml")
        additional_files += ",rain_vss.add.xml"
        print(f"Scenario 'rain': speed x0.7 on {len(edges)} arterial edges")

    cfg_path = build_sumocfg(net, routes, additional_files, end, outdir, settings["demand_scale"])
    return cfg_path, outdir / "edge_data.xml"


def run_sumo(cfg_path: Path, sumo_bin: str, step_length: float) -> None:
    cmd = [
        sumo_bin, "-c", str(cfg_path),
        "--step-length", str(step_length),
        "--no-step-log",
        "--ignore-route-errors",
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a SUMO scenario")
    parser.add_argument("--scenario", choices=SCENARIOS, default="baseline")
    parser.add_argument("--net", type=Path, required=True)
    parser.add_argument("--routes", type=Path, required=True)
    parser.add_argument("--scenarios-root", type=Path,
                        default=Path("simulation/sumo/scenarios"))
    parser.add_argument("--begin", type=int, default=0)
    parser.add_argument("--end", type=int, default=3600)
    parser.add_argument("--period", type=int, default=60, help="Edge metric aggregation period (s)")
    parser.add_argument("--step-length", type=float, default=1.0)
    parser.add_argument("--sumo-bin", default=os.environ.get("SUMO_BIN", "sumo"))
    parser.add_argument("--arterial-count", type=int, default=5)
    args = parser.parse_args()

    cfg_path, edge_data_path = prepare_scenario(
        args.scenario, args.net, args.routes, args.scenarios_root,
        args.end, args.period, args.arterial_count,
    )
    run_sumo(cfg_path, args.sumo_bin, args.step_length)
    print(f"Done. Metrics: {edge_data_path}")


if __name__ == "__main__":
    main()
