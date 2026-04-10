"""Tests for real carbon intensity data connector."""

import os
from datetime import datetime
from unittest.mock import patch

import pandas as pd
import pytest


def test_get_carbon_intensity_data_falls_back_to_synthetic():
    """When USE_REAL_CARBON_DATA=false, should return synthetic data."""
    with patch.dict(os.environ, {"USE_REAL_CARBON_DATA": "false"}, clear=False):
        # Reload config to pick up env change
        import importlib
        import config
        importlib.reload(config)

        from src.data.carbon_intensity_real import get_carbon_intensity_data
        df = get_carbon_intensity_data(datetime(2025, 1, 1), num_days=1, seed=42)

        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        # Synthetic data should NOT have "EIA" or "ENTSO-E" in source
        assert not df["source"].str.contains("EIA API").any()


def test_output_schema_matches_expected():
    """Output DataFrame must have the correct columns."""
    from src.data.carbon_intensity_real import get_carbon_intensity_data
    df = get_carbon_intensity_data(datetime(2025, 1, 1), num_days=1, seed=42)

    expected_cols = {"timestamp", "region", "intensity_gco2_kwh",
                     "intensity_lower", "intensity_upper", "source"}
    assert set(df.columns) == expected_cols


def test_region_to_source_mapping_covers_all_regions():
    """Every region in the system should have a data source mapping."""
    from src.data.carbon_intensity_real import (
        EIA_REGION_MAP, ENTSOE_REGION_MAP, EMBER_REGION_MAP,
    )
    from src.shared.models import REGIONS

    all_mapped = set(EIA_REGION_MAP) | set(ENTSOE_REGION_MAP) | set(EMBER_REGION_MAP)
    for region in REGIONS:
        assert region in all_mapped, f"Region {region} has no data source mapping"


def test_ember_static_generates_hourly_data():
    """Ember static source should produce hourly records with variation."""
    from src.data.carbon_intensity_real import _get_ember_static
    df = _get_ember_static("ap-south-1", datetime(2025, 1, 1), num_days=1, seed=42)

    assert len(df) == 24  # 1 day * 24 hours
    assert df["region"].unique().tolist() == ["ap-south-1"]
    assert "Ember" in df["source"].iloc[0]
    # Should have variation (not all same value)
    assert df["intensity_gco2_kwh"].std() > 0


def test_emission_factors_are_reasonable():
    """Emission factors should be in plausible ranges."""
    from src.data.carbon_intensity_real import EMISSION_FACTORS

    for fuel, ef in EMISSION_FACTORS.items():
        assert 0 <= ef <= 1200, f"Emission factor for {fuel} ({ef}) out of range"


def test_api_failure_falls_back_gracefully(tmp_path):
    """When API fetch fails, should fall back to synthetic for that region."""
    from src.data import carbon_intensity_real as cir
    # Override cache dir to avoid hitting real cached data
    original_cache = cir.CACHE_DIR
    cir.CACHE_DIR = tmp_path / "empty_cache"
    try:
        result = cir._fetch_eia_intensity("us-east-1", datetime(2025, 1, 1),
                                          datetime(2025, 1, 2), "invalid_key_xyz")
        # Should return None or empty DataFrame (not raise)
        assert result is None or (isinstance(result, pd.DataFrame) and len(result) == 0)
    finally:
        cir.CACHE_DIR = original_cache
