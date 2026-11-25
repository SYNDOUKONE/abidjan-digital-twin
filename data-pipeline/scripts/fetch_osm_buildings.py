"""Extract building footprints for the pilot zone via the OSM API.

Same tile-merge approach as fetch_osm_network.py but keeps closed ways tagged
building=*. Output: data/raw/abidjan_pilot.buildings.osm.xml
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data-pipeline" / "scripts"))

from fetch_osm_network import fetch_tile, tile_bbox  # noqa: E402

PILOT_BBOX = (5.330, -4.040, 5.310, -4.000)  # north, west, south, east


def write_buildings(nodes: dict[int, ET.Element], ways: dict[int, ET.Element], path: Path) -> None:
    root = ET.Element("osm", attrib={"version": "0.6", "generator": "abidjan-digital-twin/0.1"})
    for node in nodes.values():
        root.append(node)
    for way in ways.values():
        root.append(way)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch OSM buildings for the pilot zone")
    parser.add_argument("--bbox", nargs=4, type=float, default=PILOT_BBOX,
                        metavar=("NORTH", "WEST", "SOUTH", "EAST"))
    parser.add_argument("--tile-size", type=float, default=0.005)
    parser.add_argument("--out", type=Path, default=Path("data/raw/abidjan_pilot.buildings.osm.xml"))
    parser.add_argument("--sleep", type=float, default=0.5)
    args = parser.parse_args()

    north, west, south, east = args.bbox
    tiles = tile_bbox(north, west, south, east, args.tile_size)
    print(f"Fetching {len(tiles)} tiles for buildings...")

    nodes: dict[int, ET.Element] = {}
    ways: dict[int, ET.Element] = {}
    for index, (w, s, e, n) in enumerate(tiles, start=1):
        print(f"[{index}/{len(tiles)}]", flush=True)
        root = fetch_tile(w, s, e, n)
        for element in root:
            if element.tag == "node":
                nodes.setdefault(int(element.attrib["id"]), element)
            elif element.tag == "way":
                tags = {t.attrib["k"]: t.attrib["v"] for t in element.findall("tag")}
                if "building" not in tags and "building:part" not in tags:
                    continue
                refs = {int(nd.attrib["ref"]) for nd in element.findall("nd")}
                if args.out and args.out.exists():
                    pass
                ways.setdefault(int(element.attrib["id"]), element)
                way = ways[int(element.attrib["id"])]
                existing = {int(nd.attrib["ref"]) for nd in way.findall("nd")}
                for nd in element.findall("nd"):
                    if int(nd.attrib["ref"]) not in existing:
                        way.append(nd)
                        existing.add(int(nd.attrib["ref"]))
        import time
        time.sleep(args.sleep)

    keep_ways = {}
    for way_id, way in ways.items():
        refs = [int(nd.attrib["ref"]) for nd in way.findall("nd")]
        if len(refs) >= 4 and all(r in nodes for r in refs):
            keep_ways[way_id] = way
    used = {r for way in keep_ways.values() for nd in way.findall("nd") for r in [int(nd.attrib["ref"])]}
    keep_nodes = {nid: nodes[nid] for nid in used}
    print(f"Buildings: {len(keep_ways)} ways / {len(keep_nodes)} nodes")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_buildings(keep_nodes, keep_ways, args.out)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
