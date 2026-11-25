"""Extract the road network for the Abidjan pilot zone (Le Plateau) with the OSM API.

The Overpass API is not reachable from every environment, so this script uses the
official OSM API (https://api.openstreetmap.org) by tiling the bounding box, then
merges and filters the result down to highway ways.

Outputs:
  - data/raw/abidjan_pilot.osm.xml  (filtered OSM XML input for SUMO netconvert)

Usage:
  python data-pipeline/scripts/fetch_osm_network.py \
      --bbox 5.330 -4.040 5.310 -4.000 --tile-size 0.005 \
      --out data/raw/abidjan_pilot.osm.xml
"""

from __future__ import annotations

import argparse
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

OSM_API = "https://api.openstreetmap.org/api/0.6/map"
MAX_RETRIES = 3
RETRY_SLEEP_S = 5.0


def tile_bbox(
    north: float, west: float, south: float, east: float, tile_size: float
) -> list[tuple[float, float, float, float]]:
    """Split a bbox (north, west, south, east) degree caps into (west, south, east, north) tiles."""
    import math

    tiles: list[tuple[float, float, float, float]] = []
    lat_steps = int(math.ceil((north - south) / tile_size))
    lon_steps = int(math.ceil((east - west) / tile_size))
    for i in range(lat_steps):
        for j in range(lon_steps):
            lat0 = south + i * tile_size
            lat1 = min(north, south + (i + 1) * tile_size)
            lon0 = west + j * tile_size
            lon1 = min(east, west + (j + 1) * tile_size)
            tiles.append((lon0, lat0, lon1, lat1))
    return tiles


def fetch_tile(west: float, south: float, east: float, north: float) -> ET.Element:
    url = f"{OSM_API}?bbox={west:.6f},{south:.6f},{east:.6f},{north:.6f}"
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "abidjan-digital-twin/0.1"})
            with urllib.request.urlopen(request, timeout=120) as response:
                return ET.fromstring(response.read())
        except Exception as error:  # noqa: BLE001 - retry any fetch failure
            last_error = error
            if attempt < MAX_RETRIES:
                print(f"  retry {attempt}/{MAX_RETRIES} after error: {error}")
                time.sleep(RETRY_SLEEP_S)
    raise RuntimeError(f"Failed to fetch tile {url}: {last_error}")


def merge_tiles(tiles_xml: list[ET.Element]) -> tuple[dict[int, ET.Element], dict[int, ET.Element]]:
    """Merge nodes and ways across tiles, keeping the union of node refs per way."""
    nodes: dict[int, ET.Element] = {}
    ways: dict[int, ET.Element] = {}
    for root in tiles_xml:
        for element in root:
            if element.tag not in ("node", "way"):
                continue
            osm_id = int(element.attrib["id"])
            if element.tag == "node":
                nodes.setdefault(osm_id, element)
            else:
                if osm_id in ways:
                    existing_refs = {int(n.attrib["ref"]) for n in ways[osm_id].findall("nd")}
                    for nd in element.findall("nd"):
                        if int(nd.attrib["ref"]) not in existing_refs:
                            ways[osm_id].append(nd)
                            existing_refs.add(int(nd.attrib["ref"]))
                else:
                    ways[osm_id] = element
    return nodes, ways


HIGHWAY_VALUES = {
    "motorway", "trunk", "primary", "secondary", "tertiary",
    "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
    "unclassified", "residential", "living_street", "service", "road",
}


def filter_highways(
    nodes: dict[int, ET.Element], ways: dict[int, ET.Element]
) -> tuple[dict[int, ET.Element], dict[int, ET.Element]]:
    keep_ways: dict[int, ET.Element] = {}
    for way_id, way in ways.items():
        tags = {t.attrib["k"]: t.attrib["v"] for t in way.findall("tag")}
        if tags.get("highway") not in HIGHWAY_VALUES:
            continue
        if tags.get("area") == "yes":
            continue
        if tags.get("access") in ("private", "no"):
            continue
        refs = [int(nd.attrib["ref"]) for nd in way.findall("nd")]
        if not all(ref in nodes for ref in refs):
            continue
        keep_ways[way_id] = way
    used_nodes = {ref for way in keep_ways.values() for nd in way.findall("nd") for ref in [int(nd.attrib["ref"])]}
    keep_nodes = {node_id: nodes[node_id] for node_id in used_nodes}
    return keep_nodes, keep_ways


def write_osm_xml(nodes: dict[int, ET.Element], ways: dict[int, ET.Element], path: Path) -> None:
    root = ET.Element("osm", attrib={"version": "0.6", "generator": "abidjan-digital-twin/0.1"})
    for node in nodes.values():
        root.append(node)
    for way in ways.values():
        root.append(way)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch OSM network for the Abidjan pilot zone")
    parser.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("NORTH", "WEST", "SOUTH", "EAST"), help="pilot bbox")
    parser.add_argument("--tile-size", type=float, default=0.005, help="tile size in degrees")
    parser.add_argument("--out", type=Path, required=True, help="output OSM XML path")
    parser.add_argument("--sleep", type=float, default=0.5, help="delay between tile requests (seconds)")
    args = parser.parse_args()

    north, west, south, east = args.bbox
    tiles = tile_bbox(north, west, south, east, args.tile_size)
    print(f"Fetching {len(tiles)} tiles for bbox n={north} w={west} s={south} e={east}")

    tiles_xml: list[ET.Element] = []
    for index, (w, s, e, n) in enumerate(tiles, start=1):
        print(f"[{index}/{len(tiles)}] tile w={w:.4f} s={s:.4f} e={e:.4f} n={n:.4f}", flush=True)
        tiles_xml.append(fetch_tile(w, s, e, n))
        time.sleep(args.sleep)

    nodes, ways = merge_tiles(tiles_xml)
    print(f"Merged: {len(nodes)} nodes / {len(ways)} ways")
    keep_nodes, keep_ways = filter_highways(nodes, ways)
    print(f"Highway-filtered: {len(keep_nodes)} nodes / {len(keep_ways)} ways")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_osm_xml(keep_nodes, keep_ways, args.out)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
