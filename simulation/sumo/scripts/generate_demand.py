"""Generate SUMO demand for the Abidjan pilot zone.

Wraps the shipped randomTrips.py and duarouter tools:

  randomTrips.py  ->  trips.trips.xml  (origin/destination requests)
  duarouter       ->  vehicles.rou.xml (routes through the network)

Usage:
  python simulation/sumo/scripts/generate_demand.py \
      --net simulation/sumo/abidjan_pilot/network/abidjan_pilot.net.xml \
      --outdir simulation/sumo/abidjan_pilot/demand \
      --begin 0 --end 3600 --period 3.5
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def locate_sumo_home() -> Path:
    """Return the SUMO installation root (contains bin/ and tools/)."""
    import sumolib

    for candidate in (
        os.environ.get("SUMO_HOME") and Path(os.environ["SUMO_HOME"]),
        Path(sumolib.__file__).parent.parent / "sumo",
        Path(sumolib.__file__).parent,
    ):
        if candidate and (candidate / "tools" / "randomTrips.py").exists():
            return candidate
    raise SystemExit(
        "Cannot locate the SUMO installation. Set SUMO_HOME to the directory containing tools/randomTrips.py"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SUMO demand for the pilot zone")
    parser.add_argument("--net", type=Path, required=True, help="SUMO network file")
    parser.add_argument("--outdir", type=Path, required=True, help="Output directory for trips/routes")
    parser.add_argument("--begin", type=int, default=0, help="Simulation start time (s)")
    parser.add_argument("--end", type=int, default=3600, help="Simulation end time (s)")
    parser.add_argument("--period", type=float, default=3.5, help="Mean time between trips (s); lower = more demand")
    parser.add_argument("--fringe-factor", type=float, default=10.0, help="Fringe factor to favor through traffic")
    parser.add_argument("--vehicle-class", default="passenger", help="Vehicle class for generated vehicles")
    args = parser.parse_args()

    sumo_home = locate_sumo_home()
    random_trips = sumo_home / "tools" / "randomTrips.py"
    duarouter = sumo_home / "bin" / "duarouter"

    args.outdir.mkdir(parents=True, exist_ok=True)
    trips_path = args.outdir / "trips.trips.xml"
    routes_path = args.outdir / "vehicles.rou.xml"

    env = os.environ.copy()
    env.setdefault("SUMO_HOME", str(sumo_home))

    trips_cmd = [
        sys.executable,
        str(random_trips),
        "-n", str(args.net),
        "-b", str(args.begin),
        "-e", str(args.end),
        "-p", str(args.period),
        "--fringe-factor", str(args.fringe_factor),
        "-o", str(trips_path),
        "--vehicle-class", args.vehicle_class,
        "--min-distance", "200",
    ]
    print("Running:", " ".join(trips_cmd))
    subprocess.run(trips_cmd, check=True, env=env, capture_output=True, text=True)
    print(f"Wrote {trips_path}")

    routes_cmd = [
        str(duarouter),
        "-n", str(args.net),
        "--route-files", str(trips_path),
        "-o", str(routes_path),
        "--ignore-errors",
        "--repair",
    ]
    print("Running:", " ".join(routes_cmd))
    result = subprocess.run(routes_cmd, check=False, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr[-2000:])
        raise SystemExit(f"duarouter failed with code {result.returncode}")
    print(f"Wrote {routes_path}")


if __name__ == "__main__":
    main()
