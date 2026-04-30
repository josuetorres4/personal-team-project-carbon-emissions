"""Tests for the Electricity Maps connector (no real network calls)."""

import json
import os
from datetime import datetime
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest


def _reload_with_token(token: str):
    import importlib
    with patch.dict(os.environ, {"ELECTRICITYMAPS_API_TOKEN": token}, clear=False):
        import config
        importlib.reload(config)
        from src.data import electricity_maps
        importlib.reload(electricity_maps)
        return electricity_maps


def test_zone_map_covers_all_supported_regions():
    from src.data.electricity_maps import ZONE_MAP
    from src.shared.models import REGIONS

    for region in REGIONS:
        assert region in ZONE_MAP, f"Missing Electricity Maps zone for {region}"


def test_no_token_returns_empty_dict():
    em = _reload_with_token("")
    out = em.fetch_electricity_maps_intensity(datetime(2025, 1, 1), num_days=1)
    assert out == {}


def test_history_to_df_produces_correct_schema(tmp_path):
    em = _reload_with_token("dummy")
    history = [
        {"datetime": f"2025-01-01T{h:02d}:00:00.000Z",
         "carbonIntensity": 100 + h * 10}
        for h in range(0, 24)
    ]
    df = em._history_to_df(history, "us-east-1", "US-MIDA-PJM",
                           datetime(2025, 1, 1), num_days=1)

    expected = {"timestamp", "region", "intensity_gco2_kwh",
                "intensity_lower", "intensity_upper", "source"}
    assert set(df.columns) == expected
    assert len(df) == 24
    assert df["region"].unique().tolist() == ["us-east-1"]
    assert "Electricity Maps" in df["source"].iloc[0]


def test_fetch_zone_history_uses_cache(tmp_path, monkeypatch):
    em = _reload_with_token("dummy")
    monkeypatch.setattr(em, "CACHE_DIR", tmp_path)

    cache_data = [{"datetime": "2025-01-01T00:00:00.000Z", "carbonIntensity": 250}]
    cache_file = tmp_path / "em_US-MIDA-PJM.json"
    cache_file.write_text(json.dumps(cache_data))

    # is_cache_valid checks mtime; freshly written files are valid
    result = em._fetch_zone_history("US-MIDA-PJM", "dummy")
    assert result == cache_data


def test_history_skips_zero_intensity():
    em = _reload_with_token("dummy")
    history = [
        {"datetime": "2025-01-01T00:00:00.000Z", "carbonIntensity": 0},
        {"datetime": "2025-01-01T01:00:00.000Z", "carbonIntensity": None},
        {"datetime": "2025-01-01T02:00:00.000Z", "carbonIntensity": 200},
    ]
    df = em._history_to_df(history, "us-east-1", "US-MIDA-PJM",
                           datetime(2025, 1, 1), num_days=1)
    # Only valid (non-zero, non-null) records contribute to tiled output
    assert len(df) > 0
    assert (df["intensity_gco2_kwh"] > 0).all()
