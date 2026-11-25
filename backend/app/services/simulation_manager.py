"""Live SUMO simulation manager.

Runs SUMO in a background thread through TraCI, samples vehicle positions and
per-edge indicators, and keeps the latest snapshot in memory for REST / WS
consumption. Every produced record is tagged data_mode="simulated": these are
simulated vehicles, never real Abidjan traffic.
"""

from __future__ import annotations

import shutil
import threading
import time
import uuid

import sumolib
import traci

from .. import config

TICK_S = 1.0
MAX_VEHICLES_PER_SNAPSHOT = 1000
EDGE_METRIC_INTERVAL_S = 60.0


class SimulationManager:
    def __init__(self, sumo_bin: str | None = None, net_file: str | None = None):
        self.sumo_bin = sumo_bin or config.SUMO_BIN
        self.net_file = net_file or str(config.SUMO_NET_FILE)
        self._lock = threading.Lock()
        self._simulations: dict[str, dict] = {}

    # ------------------------------------------------------------------ public
    def start(self, scenario: str, duration_s: int) -> str:
        simulation_id = f"sim_{uuid.uuid4().hex[:8]}"
        state = {
            "simulation_id": simulation_id,
            "scenario": scenario,
            "duration_s": duration_s,
            "status": "queued",
            "simulation_time": 0.0,
            "vehicle_count": 0,
            "snapshot": None,
            "error": None,
        }
        with self._lock:
            self._simulations[simulation_id] = state
        thread = threading.Thread(
            target=self._run,
            args=(simulation_id,),
            daemon=True,
            name=f"sumo-{simulation_id}",
        )
        thread.start()
        return simulation_id

    def get(self, simulation_id: str) -> dict | None:
        with self._lock:
            state = self._simulations.get(simulation_id)
        if state is None:
            return None
        return {key: value for key, value in state.items() if key != "snapshot"}

    def latest_snapshot(self, simulation_id: str) -> dict | None:
        with self._lock:
            state = self._simulations.get(simulation_id)
        return state.get("snapshot") if state else None

    def active_snapshot(self) -> dict | None:
        with self._lock:
            states = list(self._simulations.values())
        running = [s for s in states if s["status"] == "running"]
        chosen = running[-1] if running else (states[-1] if states else None)
        return chosen.get("snapshot") if chosen else None

    def vehicle_positions(self) -> list[dict]:
        snapshot = self.active_snapshot()
        if snapshot is None:
            return []
        return snapshot["vehicles"]

    def sumo_available(self) -> bool:
        return shutil.which(self.sumo_bin) is not None

    # -------------------------------------------------------------------- loop
    def _convert_to_lon_lat(self, parsed_net: sumolib.net.Net, x: float, y: float) -> tuple[float, float]:
        lon, lat = parsed_net.convertXY2LonLat(x, y)
        return round(lon, 6), round(lat, 6)

    def _edge_name(self, parsed_net: sumolib.net.Net, edge_id: str) -> str | None:
        try:
            return parsed_net.getEdge(edge_id).getName() or None
        except (KeyError, AttributeError):
            return None

    def _run(self, simulation_id: str) -> None:
        with self._lock:
            state = self._simulations[simulation_id]
        scenario = state["scenario"]
        duration_s = state["duration_s"]
        cfg_path = str(config.SUMO_SCENARIOS_ROOT / scenario / "scenario.sumocfg")
        cmd = [self.sumo_bin, "-c", cfg_path, "--end", str(duration_s), "--no-step-log"]
        try:
            parsed_net = sumolib.net.readNet(str(config.SUMO_NET_FILE))
            traci.start(cmd, label=simulation_id)
            conn = traci.getConnection(label=simulation_id)
            state["status"] = "running"

            busy_edges: set[str] = set()
            edge_metrics_cache: dict[str, dict] = {}
            while conn.simulation.getMinExpectedNumber() > 0 and state["simulation_time"] < duration_s:
                conn.simulationStep()
                sim_time = conn.simulation.getTime()

                vehicles = []
                vehicle_ids = conn.vehicle.getIDList()[:MAX_VEHICLES_PER_SNAPSHOT]
                for vehicle_id in vehicle_ids:
                    x, y = conn.vehicle.getPosition(vehicle_id)
                    lon, lat = self._convert_to_lon_lat(parsed_net, x, y)
                    vehicles.append({
                        "vehicle_id": vehicle_id,
                        "edge_id": conn.vehicle.getRoadID(vehicle_id),
                        "longitude": lon,
                        "latitude": lat,
                        "heading_deg": round(conn.vehicle.getAngle(vehicle_id), 1),
                        "speed_kmh": round(conn.vehicle.getSpeed(vehicle_id) * 3.6, 1),
                        "simulation_time": sim_time,
                        "data_mode": "simulated",
                    })

                if sim_time % EDGE_METRIC_INTERVAL_S == 0:
                    for edge_id in conn.edge.getIDList():
                        if conn.edge.getLastStepVehicleNumber(edge_id) > 0:
                            busy_edges.add(edge_id)
                    edge_metrics_cache = {}
                    for edge_id in busy_edges:
                        vehicle_count = int(conn.edge.getLastStepVehicleNumber(edge_id))
                        mean_speed_kmh = round(conn.edge.getLastStepMeanSpeed(edge_id) * 3.6, 1)
                        try:
                            free_flow_kmh = round(parsed_net.getEdge(edge_id).getSpeed() * 3.6, 1)
                        except KeyError:
                            continue
                        speed_ratio = round(mean_speed_kmh / free_flow_kmh, 3) if free_flow_kmh else 0.0
                        if speed_ratio >= 0.7:
                            congestion_level = "free"
                        elif speed_ratio >= 0.4:
                            congestion_level = "moderate"
                        else:
                            congestion_level = "high"
                        edge_metrics_cache[edge_id] = {
                            "edge_id": edge_id,
                            "mean_speed_kmh": mean_speed_kmh,
                            "vehicle_count": vehicle_count,
                            "occupancy_pct": 0.0,
                            "free_flow_speed_kmh": free_flow_kmh,
                            "speed_ratio": speed_ratio,
                            "congestion_level": congestion_level,
                            "data_mode": "simulated",
                        }

                state["snapshot"] = {
                    "simulation_id": simulation_id,
                    "simulation_time": sim_time,
                    "data_mode": "simulated",
                    "vehicle_count": len(conn.vehicle.getIDList()),
                    "vehicles": vehicles,
                    "edge_metrics": list(edge_metrics_cache.values()),
                }
                state["simulation_time"] = sim_time
                state["vehicle_count"] = len(conn.vehicle.getIDList())
                time.sleep(TICK_S)

            state["status"] = "completed"
        except Exception as error:  # noqa: BLE001
            state["status"] = "failed"
            state["error"] = str(error)
        finally:
            try:
                traci.switch(simulation_id)
                traci.close()
            except Exception:  # noqa: BLE001
                pass
