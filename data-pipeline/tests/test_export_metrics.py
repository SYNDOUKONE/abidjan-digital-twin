from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

SUMO_SCRIPTS = Path(__file__).resolve().parents[2] / "simulation" / "sumo" / "scripts"
sys.path.insert(0, str(SUMO_SCRIPTS))

from export_metrics import classify_congestion, parse_edge_data  # noqa: E402


def test_classify_congestion_thresholds():
    assert classify_congestion(0.9) == "free"
    assert classify_congestion(0.7) == "free"
    assert classify_congestion(0.5) == "moderate"
    assert classify_congestion(0.4) == "moderate"
    assert classify_congestion(0.1) == "high"
    assert classify_congestion(0.0) == "high"


def test_parse_edge_data_records(tmp_path: Path):
    content = """<detector>
      <interval begin="0.00" end="60.00" id="60">
        <edge id="edge_a" sampledSeconds="10.5" traveltime="12.0" density="5.2"
              occupancy="12.40" waitingTime="3.0" speed="8.33" departed="2" arrived="1" left="3"/>
        <edge id="edge_b" sampledSeconds="30.0" speed="2.78" occupancy="45.00"
              departed="0" arrived="0" left="4"/>
      </interval>
      <interval begin="60.00" end="120.00" id="120">
        <edge id="edge_a" sampledSeconds="5.0" speed="13.90" occupancy="3.00"
              departed="1" arrived="0" left="1"/>
      </interval>
    </detector>
    """
    path = tmp_path / "edge_data.xml"
    path.write_text(content, encoding="utf-8")

    records = parse_edge_data(path)
    df = pd.DataFrame(records)
    assert len(df) == 3
    assert set(df["edge_id"]) == {"edge_a", "edge_b"}
    first = df[df["edge_id"] == "edge_a"].iloc[0]
    assert first["simulation_time_s"] == 60.0
    assert first["mean_speed_kmh"] == round(8.33 * 3.6, 2)
    assert first["vehicle_count"] == 5  # departed + left


def test_parse_edge_data_values_in_range(tmp_path: Path):
    content = """<detector>
      <interval begin="0.00" end="60.00" id="60">
        <edge id="edge_a" sampledSeconds="5.0" speed="13.90" occupancy="3.00"
              departed="1" arrived="0" left="1"/>
      </interval>
    </detector>
    """
    path = tmp_path / "edge_data.xml"
    path.write_text(content, encoding="utf-8")

    rows = pd.DataFrame(parse_edge_data(path))
    assert rows["vehicle_count"].ge(0).all()
    assert rows["mean_speed_m_s"].between(0, 60).all()
    assert set(rows["interval_end_s"]) == {60.0}
