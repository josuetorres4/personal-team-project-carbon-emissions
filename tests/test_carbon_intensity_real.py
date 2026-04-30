"""Tests for real carbon intensity data connector + Electricity Maps connector."""

import os
from datetime import datetime
from unittest.mock import patch

import pandas as pd
import pytest


def _reload_config_with(env: dict):
    """Helper: patch env, reload config so it picks up the new vars."""
    import importlib
    with patch.dict(os.environ, env, clear=False):
        import config
        importlib.reload(config)
        return config


def test_real_data_only_raises_when_keys_missing():
    """REAL_DATA_ONLY=true with no Electricity Maps / EIA / ENTSO-E keys must raise."""
    cfg = _reload_config_with({
        "REAL_DATA_ONLY": "true",
        "USE_REAL_CARBON_DATA": "true",
        "ELECTRICITYMAPS_API_TOKEN": "",
        "EIA_API_KEY": "",
        "ENTSOE_API_TOKEN": "",
    })
    # Reload the module that reads the config
    import importlib
    from src.data import carbon_intensity_real
    importlib.reload(carbon_intensity_real)

    with pytest.raises(RuntimeError):
        carbon_intensity_real.get_carbon_intensity_data(
            datetime(2025, 1, 1), num_days=1, seed=42
        )


def test_real_data_only_requires_use_real_carbon_data_flag():
    """REAL_DATA_ONLY=true with USE_REAL_CARBON_DATA=false must raise immediately."""
    _reload_config_with({
        "REAL_DATA_ONLY": "true",
        "USE_REAL_CARBON_DATA": "false",
    })
    import importlib
    from src.data import carbon_intensity_real
    importlib.reload(carbon_intensity_real)

    with pytest.raises(RuntimeError, match="USE_REAL_CARBON_DATA=true"):
        carbon_intensity_real.get_carbon_intensity_data(
            datetime(2025, 1, 1), num_days=1, seed=42
        )


def test_legacy_mode_still_falls_back_to_synthetic():
    """REAL_DATA_ONLY=false must keep the original fallback-to-synthetic path."""
    _reload_config_with({
        "REAL_DATA_ONLY": "false",
        "USE_REAL_CARBON_DATA": "false",
    })
    import importlib
    from src.data import carbon_intensity_real
    importlib.reload(carbon_intensity_real)

    df = carbon_intensity_real.get_carbon_intensity_data(
        datetime(2025, 1, 1), num_days=1, seed=42
    )

    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0
    # Synthetic data should NOT have "EIA API" or "Electricity Maps" in source
    assert not df["source"].str.contains("EIA API").any()
    assert not df["source"].str.contains("Electricity Maps").any()


def test_output_schema_matches_expected():
    """Output DataFrame must have the correct columns regardless of source."""
    _reload_config_with({
        "REAL_DATA_ONLY": "false",
        "USE_REAL_CARBON_DATA": "false",
    })
    import importlib
    from src.data import carbon_intensity_real
    importlib.reload(carbon_intensity_real)

    df = carbon_intensity_real.get_carbon_intensity_data(
        datetime(2025, 1, 1), num_days=1, seed=42
    )

    expected_cols = {"timestamp", "region", "intensity_gco2_kwh",
                     "intensity_lower", "intensity_upper", "source"}
    assert set(df.columns) == expected_cols


def test_region_to_source_mapping_covers_all_regions():
    """Every region in the system has at least one real data source mapping."""
    from src.data.carbon_intensity_real import (
        EIA_REGION_MAP, ENTSOE_REGION_MAP, EMBER_REGION_MAP,
    )
    from src.data.electricity_maps import ZONE_MAP
    from src.shared.models import REGIONS

    all_mapped = (
        set(EIA_REGION_MAP) | set(ENTSOE_REGION_MAP)
        | set(EMBER_REGION_MAP) | set(ZONE_MAP)
    )
    for region in REGIONS:
        assert region in all_mapped, f"Region {region} has no real data source mapping"


def test_electricity_maps_covers_all_regions():
    """Electricity Maps zone map must cover every supported region as the primary source."""
    from src.data.electricity_maps import ZONE_MAP
    from src.shared.models import REGIONS

    for region in REGIONS:
        assert region in ZONE_MAP, f"Region {region} missing from Electricity Maps zone map"


def test_emission_factors_are_reasonable():
    """Emission factors should be in plausible ranges."""
    from src.data.carbon_intensity_real import EMISSION_FACTORS

    for fuel, ef in EMISSION_FACTORS.items():
        assert 0 <= ef <= 1200, f"Emission factor for {fuel} ({ef}) out of range"


def test_electricity_maps_returns_empty_without_token():
    """fetch_electricity_maps_intensity returns {} when no token is configured."""
    _reload_config_with({"ELECTRICITYMAPS_API_TOKEN": ""})
    import importlib
    from src.data import electricity_maps
    importlib.reload(electricity_maps)

    result = electricity_maps.fetch_electricity_maps_intensity(
        datetime(2025, 1, 1), num_days=1
    )
    assert result == {}
