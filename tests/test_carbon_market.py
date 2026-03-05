"""
Tests for src/shared/carbon_market.py

Covers CarbonMarket initialization, emission recording, saving recording,
trade proposals, trade approvals, surplus/deficit finding, and serialization.
"""

import pytest
from src.shared.carbon_market import CarbonMarket, CarbonBudget, CarbonTrade


class TestCarbonBudget:
    def test_surplus_calculation(self):
        b = CarbonBudget(team="team-a", week="2026-W10", allocated_kg=500.0)
        assert b.surplus_kg == 500.0

    def test_surplus_with_spending(self):
        b = CarbonBudget(team="team-a", week="2026-W10", allocated_kg=500.0, spent_kg=200.0)
        assert b.surplus_kg == 300.0

    def test_surplus_with_trades(self):
        b = CarbonBudget(team="team-a", week="2026-W10", allocated_kg=500.0, spent_kg=200.0, traded_kg=50.0)
        assert b.surplus_kg == 350.0

    def test_deficit_when_overspent(self):
        b = CarbonBudget(team="team-a", week="2026-W10", allocated_kg=500.0, spent_kg=600.0)
        assert b.surplus_kg == -100.0

    def test_efficiency_score_zero_allocation(self):
        b = CarbonBudget(team="team-a", week="2026-W10", allocated_kg=0)
        assert b.efficiency_score == 0

    def test_efficiency_score_with_savings(self):
        b = CarbonBudget(team="team-a", week="2026-W10", allocated_kg=500.0, saved_kg=250.0)
        assert b.efficiency_score == 50.0

    def test_efficiency_score_capped_at_100(self):
        b = CarbonBudget(team="team-a", week="2026-W10", allocated_kg=100.0, saved_kg=200.0)
        assert b.efficiency_score == 100


class TestCarbonMarket:
    def test_initialization(self):
        market = CarbonMarket(teams=["team-a", "team-b"], weekly_budget_kg=500.0)
        assert len(market.budgets) == 2
        assert "team-a" in market.budgets
        assert "team-b" in market.budgets
        assert market.budgets["team-a"].allocated_kg == 500.0

    def test_record_emission(self):
        market = CarbonMarket(teams=["team-a"], weekly_budget_kg=500.0)
        market.record_emission("team-a", 100.0)
        assert market.budgets["team-a"].spent_kg == 100.0

    def test_record_emission_unknown_team(self):
        market = CarbonMarket(teams=["team-a"], weekly_budget_kg=500.0)
        market.record_emission("unknown", 100.0)  # Should not raise

    def test_record_saving(self):
        market = CarbonMarket(teams=["team-a"], weekly_budget_kg=500.0)
        market.record_saving("team-a", 50.0, verified=True)
        assert market.budgets["team-a"].saved_kg == 50.0
        assert market.budgets["team-a"].carbon_credits > 0

    def test_record_saving_unverified(self):
        market = CarbonMarket(teams=["team-a"], weekly_budget_kg=500.0)
        market.record_saving("team-a", 50.0, verified=False)
        assert market.budgets["team-a"].saved_kg == 0.0

    def test_find_surplus_teams(self):
        market = CarbonMarket(teams=["team-a", "team-b"], weekly_budget_kg=500.0)
        market.record_emission("team-a", 100.0)  # surplus = 400
        market.record_emission("team-b", 600.0)  # deficit = -100
        surplus = market.find_surplus_teams()
        assert len(surplus) == 1
        assert surplus[0][0] == "team-a"

    def test_find_deficit_teams(self):
        market = CarbonMarket(teams=["team-a", "team-b"], weekly_budget_kg=500.0)
        market.record_emission("team-b", 600.0)
        deficit = market.find_deficit_teams()
        assert len(deficit) == 1
        assert deficit[0][0] == "team-b"

    def test_propose_trade(self):
        market = CarbonMarket(teams=["team-a", "team-b"], weekly_budget_kg=500.0)
        trade = market.propose_trade("team-a", "team-b", 100.0)
        assert trade.from_team == "team-a"
        assert trade.to_team == "team-b"
        assert trade.kg_traded == 100.0
        assert trade.status == "proposed"

    def test_approve_trade(self):
        market = CarbonMarket(teams=["team-a", "team-b"], weekly_budget_kg=500.0)
        trade = market.propose_trade("team-a", "team-b", 100.0)
        market.approve_trade(trade.trade_id)
        assert trade.status == "approved"
        assert market.budgets["team-a"].traded_kg == -100.0
        assert market.budgets["team-b"].traded_kg == 100.0

    def test_approve_nonexistent_trade(self):
        market = CarbonMarket(teams=["team-a"], weekly_budget_kg=500.0)
        with pytest.raises(ValueError):
            market.approve_trade("nonexistent")

    def test_to_dict(self):
        market = CarbonMarket(teams=["team-a", "team-b"], weekly_budget_kg=500.0)
        d = market.to_dict()
        assert "week" in d
        assert "budgets" in d
        assert "trades" in d
        assert "market_summary" in d
        assert d["market_summary"]["total_teams"] == 2

    def test_save(self, tmp_path):
        market = CarbonMarket(teams=["team-a"], weekly_budget_kg=500.0)
        path = str(tmp_path / "market.json")
        market.save(path)
        import json
        with open(path) as f:
            data = json.load(f)
        assert data["market_summary"]["total_teams"] == 1
