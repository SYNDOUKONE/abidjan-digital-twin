from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = REPO_ROOT / "data" / "processed"


@pytest.fixture(scope="session")
def baseline_frame() -> pd.DataFrame:
    path = PROCESSED_DIR / "traffic_60s_baseline.parquet"
    if not path.exists():
        pytest.skip("Baseline parquet not generated yet")
    return pd.read_parquet(path)


@pytest.fixture()
def client(baseline_frame):
    from backend.app import config, main
    from backend.app.services import traffic_store

    os.environ["ADT_DATA_DIR"] = str(PROCESSED_DIR)
    config.DATA_DIR = PROCESSED_DIR
    traffic_store.get_store.cache_clear()

    with TestClient(main.app) as test_client:
        yield test_client
