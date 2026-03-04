"""
Tests for src/shared/impact.py

Covers equivalency calculations (known inputs → expected outputs),
business impact calculations, and edge cases.
"""

import pytest
from src.shared.impact import compute_equivalencies, compute_business_impact


class TestComputeEquivalencies:
    def test_zero_savings_returns_empty(self):
        result = compute_equivalencies(0.0)
        assert result == []

    def test_negative_savings_returns_empty(self):
        result = compute_equivalencies(-5.0)
        assert result == []

    def test_returns_top_3_by_default(self):
        result = compute_equivalencies(100.0)
        assert len(result) == 3

    def test_custom_top_n(self):
        result = compute_equivalencies(100.0, top_n=2)
        assert len(result) == 2

    def test_known_miles_calculation(self):
        # 0.404 kgCO₂/mile → 40.4 kg = 100 miles
        result = compute_equivalencies(40.4)
        miles_entry = next((r for r in result if r["id"] == "miles_not_driven"), None)
        if miles_entry:
            assert abs(miles_entry["value"] - 100.0) < 0.1

    def test_known_smartphones_calculation(self):
        # 0.008 kgCO₂/charge → 0.008 kg = 1 charge
        result = compute_equivalencies(0.008, top_n=5)
        phones_entry = next((r for r in result if r["id"] == "smartphones_charged"), None)
        if phones_entry:
            assert abs(phones_entry["value"] - 1.0) < 0.01

    def test_known_tree_calculation(self):
        # 60 kgCO₂/tree → 60 kg = 1 tree
        result = compute_equivalencies(60.0, top_n=5)
        tree_entry = next((r for r in result if r["id"] == "tree_seedlings_10yr"), None)
        if tree_entry:
            assert abs(tree_entry["value"] - 1.0) < 0.01

    def test_result_structure(self):
        result = compute_equivalencies(50.0)
        for item in result:
            assert "id" in item
            assert "label" in item
            assert "value" in item
            assert "unit" in item
            assert "icon" in item
            assert isinstance(item["value"], float)

    def test_large_savings(self):
        # 1000 kg → reasonable numbers
        result = compute_equivalencies(1000.0)
        assert len(result) == 3
        for item in result:
            assert item["value"] > 0


class TestComputeBusinessImpact:
    def test_basic_structure(self):
        result = compute_business_impact(
            kg_co2e_saved=100.0,
            cost_change_usd=10.0,
            total_cloud_spend=1000.0,
        )
        assert "monthly" in result
        assert "annual_projection" in result
        assert "equivalencies" in result
        assert "carbon_pricing_scenarios" in result
        assert "efficiency" in result

    def test_monthly_values(self):
        result = compute_business_impact(
            kg_co2e_saved=100.0,
            cost_change_usd=5.0,
            total_cloud_spend=500.0,
        )
        monthly = result["monthly"]
        assert monthly["kg_co2e_saved"] == 100.0
        assert monthly["tons_co2e_saved"] == pytest.approx(0.1, abs=1e-5)
        assert monthly["cost_change_usd"] == 5.0
        assert monthly["cost_change_pct"] == pytest.approx(1.0, abs=0.01)

    def test_annual_projection_default_factor_12(self):
        result = compute_business_impact(
            kg_co2e_saved=100.0,
            cost_change_usd=10.0,
            total_cloud_spend=1000.0,
        )
        annual = result["annual_projection"]
        assert annual["kg_co2e_saved"] == pytest.approx(1200.0, abs=0.1)
        assert annual["cost_change_usd"] == pytest.approx(120.0, abs=0.1)

    def test_custom_annualize_factor(self):
        result = compute_business_impact(
            kg_co2e_saved=100.0,
            cost_change_usd=10.0,
            total_cloud_spend=1000.0,
            annualize_factor=6,
        )
        annual = result["annual_projection"]
        assert annual["kg_co2e_saved"] == pytest.approx(600.0, abs=0.1)

    def test_pricing_scenarios_count(self):
        result = compute_business_impact(100.0, 0.0, 1000.0)
        scenarios = result["carbon_pricing_scenarios"]
        assert len(scenarios) == 4

    def test_pricing_scenario_values(self):
        result = compute_business_impact(
            kg_co2e_saved=1000.0,  # 1 ton
            cost_change_usd=0.0,
            total_cloud_spend=1000.0,
        )
        eu_ets = next(
            s for s in result["carbon_pricing_scenarios"]
            if "EU ETS 2025" in s["scenario"]
        )
        assert eu_ets["usd_per_ton"] == 75.0
        assert eu_ets["monthly_value_usd"] == pytest.approx(75.0, abs=0.01)
        assert eu_ets["annual_value_usd"] == pytest.approx(900.0, abs=0.01)

    def test_zero_savings_edge_case(self):
        result = compute_business_impact(0.0, 0.0, 1000.0)
        assert result["monthly"]["kg_co2e_saved"] == 0.0
        assert result["equivalencies"] == []
        assert result["efficiency"]["break_even_carbon_price_usd_per_ton"] is None
        assert result["efficiency"]["kg_co2e_per_dollar_extra_cost"] is None

    def test_zero_cost_increase_edge_case(self):
        result = compute_business_impact(100.0, 0.0, 1000.0)
        assert result["efficiency"]["break_even_carbon_price_usd_per_ton"] is None
        assert result["efficiency"]["kg_co2e_per_dollar_extra_cost"] is None

    def test_break_even_calculation(self):
        # 10 kg saved (0.01 ton), $1 extra cost → break-even = $100/ton
        result = compute_business_impact(10.0, 1.0, 1000.0)
        be = result["efficiency"]["break_even_carbon_price_usd_per_ton"]
        assert be == pytest.approx(100.0, abs=0.5)

    def test_efficiency_calculation(self):
        # 10 kg saved, $2 extra cost → 5 kg/dollar
        result = compute_business_impact(10.0, 2.0, 1000.0)
        eff = result["efficiency"]["kg_co2e_per_dollar_extra_cost"]
        assert eff == pytest.approx(5.0, abs=0.01)

    def test_zero_cloud_spend(self):
        result = compute_business_impact(100.0, 10.0, 0.0)
        assert result["monthly"]["cost_change_pct"] == 0.0
