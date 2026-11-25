"""Build a self-contained interactive 3D viewer (Three.js) of the pilot zone.

The HTML embeds:
  - the SUMO road network (WGS84 -> local meters, same convention as the UE5 client)
  - OSM building footprints extruded to 3D
  - per-edge congestion coloring from the baseline Parquet (data_mode=simulated)
  - animated vehicle positions sampled live from a SUMO run via TraCI

Camera: orbit + zoom (mouse). Playback: play/pause + speed, 1x/8x/30x.

Usage:
  LD_LIBRARY_PATH=... python visualization/build_3d_viewer.py \
      --net simulation/sumo/abidjan_pilot/network/abidjan_pilot.net.xml \
      --buildings data/raw/abidjan_pilot.buildings.osm.xml \
      --data-dir data/processed --outdir docs/visuals \
      --sumo-bin sumo
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import pandas as pd
import sumolib

LON0, LAT0 = -4.0206, 5.3217  # Le Plateau
M_PER_DEG_LAT = 110_574.0
M_PER_DEG_LON = 111_320.0 * math.cos(math.radians(LAT0))

RATIO_COLORS = [
    (0.00, "#e74c3c"),
    (0.40, "#e67e22"),
    (0.70, "#2ecc71"),
    (1.05, "#7fd39a"),
]


def lonlat_to_local(lon: float, lat: float) -> tuple[float, float]:
    x = (lon - LON0) * M_PER_DEG_LON
    y = (lat - LAT0) * M_PER_DEG_LAT
    return round(x, 1), round(y, 1)


def ratio_to_color(ratio: float | None) -> tuple[float, float, float]:
    if ratio is None:
        hex_color = "#95a5a6"
    else:
        hex_color = RATIO_COLORS[0][1]
        for threshold, candidate in RATIO_COLORS:
            if ratio >= threshold:
                hex_color = candidate
    value = int(hex_color[1:], 16)
    return ((value >> 16) & 255) / 255, ((value >> 8) & 255) / 255, (value & 255) / 255


def collect_edges(net: sumolib.net.Net) -> list[list]:
    segments = []
    for edge in net.getEdges():
        if edge.isSpecial() or edge.getFromNode() == edge.getToNode():
            continue
        points = [lonlat_to_local(*net.convertXY2LonLat(x, y)) for x, y in edge.getShape()]
        if len(points) < 2:
            continue
        flat = [value for point in points for value in point]
        segments.append(flat)
    return segments


def collect_buildings(path: Path) -> tuple[list[list], list[float]]:
    root = ET.parse(path).getroot()
    nodes = {
        int(el.attrib["id"]): (float(el.attrib["lon"]), float(el.attrib["lat"]))
        for el in root if el.tag == "node"
    }
    polys, heights = [], []
    for way in root:
        if way.tag != "way":
            continue
        rings = [int(n.attrib["ref"]) for n in way.findall("nd")]
        if len(rings) < 4 or any(r not in nodes for r in rings):
            continue
        levels = None
        for tag in way.findall("tag"):
            if tag.attrib["k"] == "building:levels":
                try:
                    levels = float(tag.attrib["v"])
                except ValueError:
                    pass
        digest = int(hashlib.md5(way.attrib["id"].encode()).hexdigest()[:8], 16)
        if levels:
            height = 3.0 * levels
        else:
            height = 9.0 + (digest % 5) * 4.0  # 9-25 m deterministic per building
        footprint = [coord for ref in rings[:-1] for coord in lonlat_to_local(*nodes[ref])]
        polys.append(footprint)
        heights.append(round(height, 1))
    return polys, heights


def sample_frames(net: sumolib.net.Net, cfg: Path, sumo_bin: str,
                  duration_s: int = 300, step_every: int = 3, demand_scale: float = 1.0) -> dict:
    import traci

    cmd = [sumo_bin, "-c", str(cfg), "--end", str(duration_s), "--no-step-log", "--ignore-route-errors",
           "--scale", str(demand_scale)]
    frames_t: list[float] = []
    frames_vehicles: list[list[list[float]]] = []
    try:
        traci.start(cmd, label="viz3d")
        conn = traci.getConnection(label="viz3d")
        sim_time = 0.0
        while sim_time < duration_s and conn.simulation.getMinExpectedNumber() > 0:
            conn.simulationStep()
            sim_time = conn.simulation.getTime()
            if int(sim_time) % step_every != 0:
                continue
            entries = []
            for vehicle_id in conn.vehicle.getIDList():
                x, y = conn.vehicle.getPosition(vehicle_id)
                lon, lat = net.convertXY2LonLat(x, y)
                px, py = lonlat_to_local(lon, lat)
                entries.append([px, py, round(conn.vehicle.getSpeed(vehicle_id) * 3.6, 1)])
            frames_t.append(sim_time)
            frames_vehicles.append(entries)
    finally:
        try:
            traci.close()
        except Exception:
            pass
    return {"t": frames_t, "vehicles": frames_vehicles}


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Abidjan Digital Twin — pilot Le Plateau (3D)</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body { margin: 0; overflow: hidden; font-family: system-ui, sans-serif; background: #0b0f14; }
  #hud { position: fixed; top: 10px; left: 10px; color: #ecf0f1; background: rgba(13,17,23,.82);
         padding: 10px 14px; border-radius: 8px; font-size: 13px; max-width: 340px; }
  #hud h1 { font-size: 15px; margin: 0 0 4px; }
  #hud .mode { color: #f39c12; font-weight: 600; }
  #legend { position: fixed; bottom: 12px; left: 10px; color: #ecf0f1; background: rgba(13,17,23,.82);
            padding: 8px 12px; border-radius: 8px; font-size: 12px; }
  #controls { position: fixed; bottom: 12px; right: 10px; background: rgba(13,17,23,.82);
              padding: 8px 12px; border-radius: 8px; color: #ecf0f1; font-size: 13px; }
  #controls button { background: #2980b9; border: 0; color: #fff; border-radius: 4px;
                     padding: 4px 10px; margin: 0 3px; cursor: pointer; }
  #info { margin-top: 6px; color: #bdc3c7; }
  a { color: #7fb3d5; }
</style>
</head>
<body>
<div id="hud">
  <h1>Abidjan Digital Twin — Milestone 1</h1>
  <div>Zone pilote : <strong>Le Plateau</strong> (<span>lon __LON0__, lat __LAT0__</span>)</div>
  <div class="mode">⚠ Données 100&nbsp;% simulées (SUMO + OSM) — pas de trafic réel</div>
  <div id="info">__INFO__</div>
  <div>Modèle 3D équivalent UE5/Césium : mêmes coordonnées WGS84, zone <code>edge_id</code> commune.</div>
</div>
<div id="legend">
  <strong>Ratio vitesse / flux libre</strong><br>
  <span style="color:#e74c3c">■</span> congestionné &lt; 0,4 &nbsp;
  <span style="color:#e67e22">■</span> dense 0,4–0,7 &nbsp;
  <span style="color:#2ecc71">■</span> fluide ≥ 0,7 &nbsp;
  <span style="color:#95a5a6">■</span> sans trafic
</div>
<div id="controls">
  <button id="play">⏸︎ Pause</button>
  <button data-speed="1">1×</button>
  <button data-speed="8">8×</button>
  <button data-speed="30">30×</button>
  <span id="tlabel"></span>
</div>
<script type="importmap">
  {"imports": {"three": "https://unpkg.com/three@0.161.0/build/three.module.js",
               "three/addons/": "https://unpkg.com/three@0.161.0/examples/jsm/"}}
</script>
<script type="module">
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

const DATA = __DATA__;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0b0f14);
scene.fog = new THREE.Fog(0x0b0f14, 3000, 12000);

const camera = new THREE.PerspectiveCamera(60, innerWidth/innerHeight, 1, 30000);
camera.position.set(200, 900, 1400);

const renderer = new THREE.WebGLRenderer({antialias: true});
renderer.setSize(innerWidth, innerHeight);
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
document.body.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 0, 0);

scene.add(new THREE.HemisphereLight(0xbfd4e2, 0x2c3e50, 1.1));
const sun = new THREE.DirectionalLight(0xffffff, 1.2);
sun.position.set(1200, 2000, 800);
scene.add(sun);

// --- roads (LineSegments, vertex colors by congestion ratio) ---
{
  const positions = [], colors = [];
  DATA.edges.segs.forEach((seg, i) => {
    const ratio = DATA.edges.ratios[i];
    const c = new THREE.Color();
    if (ratio === null) c.set('#95a5a6');
    else if (ratio < 0.4) c.set('#e74c3c');
    else if (ratio < 0.7) c.set('#e67e22');
    else c.set('#2ecc71');
    for (let k = 0; k < seg.length - 2; k += 2) {
      positions.push(seg[k], 0.4, -seg[k+1], seg[k+2], 0.4, -seg[k+3]);
      colors.push(c.r, c.g, c.b, c.r, c.g, c.b);
    }
  });
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
  scene.add(new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({vertexColors: true, transparent: true, opacity: 0.95})));
}

// --- buildings (extruded footprints, merged) ---
{
  const geoms = [];
  DATA.buildings.polys.forEach((poly, i) => {
    const shape = new THREE.Shape(poly.reduce((acc, _, k) => {
      if (k % 2 === 0) acc.push(new THREE.Vector2(poly[k], poly[k+1]));
      return acc;
    }, []));
    const geometry = new THREE.ExtrudeGeometry(shape, {depth: DATA.buildings.heights[i], bevelEnabled: false});
    geometry.rotateX(-Math.PI / 2);
    geoms.push(geometry);
  });
  const merged = mergeGeometries(geoms);
  const material = new THREE.MeshLambertMaterial({color: 0x8fa3b0});
  scene.add(new THREE.Mesh(merged, material));
}

// --- vehicles (InstancedMesh) ---
const vehicleMesh = new THREE.InstancedMesh(
  new THREE.BoxGeometry(6, 2.6, 3),
  new THREE.MeshLambertMaterial({color: 0xf7f9f9}),
  DATA.frames.vehicles.reduce((m, f) => Math.max(m, f.length), 0)
);
vehicleMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
scene.add(vehicleMesh);

let playing = true, speed = 8, simT = 0;
const playBtn = document.getElementById('play');
playBtn.onclick = () => { playing = !playing; playBtn.textContent = playing ? '⏸︎ Pause' : '▶︎ Play'; };
document.querySelectorAll('#controls button[data-speed]').forEach(b => {
  b.onclick = () => { speed = Number(b.dataset.speed); };
});
const clock = new THREE.Clock();
const endTime = DATA.frames.t.length - 1;
const dummy = new THREE.Object3D();

function scatterColor(v) { return v > 30 ? 0xe67e22 : (v < 10 ? 0xe74c3c : 0xf7f9f9); }

function drawFrame(dtSeconds) {
  simT += playing ? dtSeconds * speed : 0;
  const tMax = DATA.frames.t[endTime];
  if (simT > tMax) simT = 0;
  const idx = Math.min(endTime, Math.max(0, DATA.frames.t.findIndex(t => t >= simT)));
  const frame = DATA.frames.vehicles[idx];
  const count = frame.length;
  for (let i = 0; i < vehicleMesh.count; i++) {
    if (i < count) {
      dummy.position.set(frame[i][0], 2, -frame[i][1]);
      dummy.updateMatrix();
      vehicleMesh.setMatrixAt(i, dummy.matrix);
      vehicleMesh.setColorAt(i, new THREE.Color(scatterColor(frame[i][2])));
    } else {
      dummy.position.set(0, -50, 0);
      dummy.updateMatrix();
      vehicleMesh.setMatrixAt(i, dummy.matrix);
    }
  }
  vehicleMesh.instanceMatrix.needsUpdate = true;
  if (vehicleMesh.instanceColor) vehicleMesh.instanceColor.needsUpdate = true;
  document.getElementById('tlabel').textContent = `t=${Math.round(simT)} s — ${count} véhicules`;
}

function animate() {
  requestAnimationFrame(animate);
  const dt = clock.getDelta();
  controls.update();
  drawFrame(dt);
  renderer.render(scene, camera);
}
animate();

addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});
</script>
</body>
</html>
"""


def build_html(edges: list[list], ratios: dict[str, float], polys: list[list],
               heights: list[float], frames: dict, out_path: Path, edge_ids: list[str]) -> None:
    seg_ratios = [ratios.get(edge_id) for edge_id in edge_ids]
    payload = {
        "edges": {"segs": edges, "ratios": seg_ratios},
        "buildings": {"polys": polys, "heights": heights},
        "frames": frames,
    }
    html = (HTML_TEMPLATE
            .replace("__DATA__", json.dumps(payload, separators=(",", ":")))
            .replace("__LON0__", str(LON0))
            .replace("__LAT0__", str(LAT0))
            .replace("__INFO__",
                     f"{len(polys)} bâtiments OSM · {len(edges)} segments routiers SUMO · "
                     f"replay {frames['t'][-1]:.0f} s"))
    out_path.write_text(html, encoding="utf-8")
    print(f"wrote {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the interactive 3D HTML viewer")
    parser.add_argument("--net", type=Path, required=True)
    parser.add_argument("--buildings", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--outdir", type=Path, default=Path("docs/visuals"))
    parser.add_argument("--baseline-cfg", type=Path,
                        default=Path("simulation/sumo/scenarios/baseline/scenario.sumocfg"))
    parser.add_argument("--sumo-bin", default=os.environ.get("SUMO_BIN", "sumo"))
    parser.add_argument("--duration", type=int, default=300)
    parser.add_argument("--step", type=int, default=3)
    parser.add_argument("--demand-scale", type=float, default=1.0)
    args = parser.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)
    net = sumolib.net.readNet(str(args.net))

    edges, edge_ids = [], []
    for edge in net.getEdges():
        if edge.isSpecial() or edge.getFromNode() == edge.getToNode():
            continue
        points = [lonlat_to_local(*net.convertXY2LonLat(x, y)) for x, y in edge.getShape()]
        if len(points) >= 2:
            edges.append([value for p in points for value in p])
            edge_ids.append(edge.getID())

    df = pd.read_parquet(args.data_dir / "traffic_60s_baseline.parquet")
    ratios = df.groupby("edge_id")["speed_ratio"].mean().round(3).to_dict()

    polys, heights = collect_buildings(args.buildings)
    print(f"{len(edges)} edges / {len(polys)} buildings")

    frames = sample_frames(net, args.baseline_cfg, args.sumo_bin, args.duration, args.step, args.demand_scale)
    print(f"{len(frames['t'])} frames, max {max(len(f) for f in frames['vehicles'])} vehicles/frame")

    build_html(edges, ratios, polys, heights, frames, args.outdir / "traffic_3d.html", edge_ids)


if __name__ == "__main__":
    main()
