"""
Tests for src/data/carbon_intensity_provider.py

Covers synthetic fallback and the get_carbon_intensity entry point.
Note: Real API tests are skipped to avoid network dependency.
"""

import pytest
import pandas as pd
from src.data.carbon_intensity_provider import _synthetic_fallback, get_carbon_intensity


class TestSyntheticFallback:
    def test_returns_dataframe(self):
        df = _synthetic_fallback(24)
        assert isinstance(df, pd.DataFrame)

    def test_columns_present(self):
        df = _synthetic_fallback(24)
        expected_cols = {"timestamp", "carbon_intensity_gco2_kwh", "source", "is_real", "region"}
        assert expected_cols.issubset(set(df.columns))

    def test_correct_row_count(self):
        df = _synthetic_fallback(24)
        assert len(df) == 48  # 24 hours * 2 (30-min intervals)

    def test_all_synthetic_flags(self):
        df = _synthetic_fallback(24)
        assert all(df["is_real"] == False)
        assert all(df["source"] == "synthetic")
        assert all(df["region"] == "synthetic")

    def test_intensity_range(self):
        df = _synthetic_fallback(48)
        assert df["carbon_intensity_gco2_kwh"].min() >= 50
        assert df["carbon_intensity_gco2_kwh"].max() <= 600


class TestGetCarbonIntensity:
    def test_returns_dataframe(self):
        # This will fall back to synthetic if no cache and no network
        df = get_carbon_intensity(hours=24)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_has_required_columns(self):
        df = get_carbon_intensity(hours=24)
        expected_cols = {"timestamp", "carbon_intensity_gco2_kwh", "source", "is_real", "region"}
        assert expected_cols.issubset(set(df.columns))
