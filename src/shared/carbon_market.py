"""
Carbon Market — internal carbon currency system.
Teams receive weekly carbon budgets (kgCO2e) and can trade surplus/deficit.
"""
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CarbonBudget:
    team: str
    week: str                        # ISO week e.g. "2026-W10"
    allocated_kg: float              # budget assigned by Governance
    spent_kg: float = 0.0           # actual emissions this week
    saved_kg: float = 0.0           # verified savings achieved
    traded_kg: float = 0.0          # net traded (positive = received, negative = gave away)
    carbon_credits: float = 0.0     # earned credits from verified savings

    @property
    def surplus_kg(self) -> float:
        return self.allocated_kg - self.spent_kg + self.traded_kg

    @property
    def efficiency_score(self) -> float:
        """0-100 score: how well did the team use their budget?"""
        if self.allocated_kg == 0:
            return 0
        return min(100, (self.saved_kg / self.allocated_kg) * 100)


@dataclass
class CarbonTrade:
    trade_id: str
    from_team: str
    to_team: str
    kg_traded: float
    price_per_kg: float              # internal carbon price (USD)
    reason: str                      # why the trade was proposed
    status: str = "proposed"        # proposed | approved | rejected
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    approved_by: Optional[str] = None


class CarbonMarket:
    """
    Internal carbon trading marketplace.
    The Copilot agent acts as the broker — it identifies teams with
    surplus budgets and proposes trades to teams running over.
    """
    INTERNAL_CARBON_PRICE_USD_PER_KG = 0.075  # $75/ton = $0.075/kg

    def __init__(self, teams: list, weekly_budget_kg: float = 500.0):
        self.teams = teams
        self.weekly_budget_kg = weekly_budget_kg
        self.budgets: dict = {}
        self.trades: list = []
        self.week = datetime.utcnow().strftime("%Y-W%W")
        self._initialize_budgets()

    def _initialize_budgets(self):
        for team in self.teams:
            self.budgets[team] = CarbonBudget(
                team=team,
                week=self.week,
                allocated_kg=self.weekly_budget_kg
            )
        logger.info(f"Carbon market initialized: {len(self.teams)} teams, {self.weekly_budget_kg}kg budget each")

    def record_emission(self, team: str, kg: float):
        if team in self.budgets:
            self.budgets[team].spent_kg += kg

    def record_saving(self, team: str, kg: float, verified: bool = True):
        if team in self.budgets and verified:
            self.budgets[team].saved_kg += kg
            # Award carbon credits for verified savings
            credits = kg * self.INTERNAL_CARBON_PRICE_USD_PER_KG
            self.budgets[team].carbon_credits += credits

    def find_surplus_teams(self) -> list:
        """Teams with more budget than they're using."""
        return [
            (team, b.surplus_kg)
            for team, b in self.budgets.items()
            if b.surplus_kg > 50  # only meaningful surplus
        ]

    def find_deficit_teams(self) -> list:
        """Teams running over their budget."""
        return [
            (team, abs(b.surplus_kg))
            for team, b in self.budgets.items()
            if b.surplus_kg < 0
        ]

    def propose_trade(self, from_team: str, to_team: str, kg: float) -> CarbonTrade:
        """Copilot agent calls this to propose a trade between teams."""
        trade = CarbonTrade(
            trade_id=f"trade_{len(self.trades)+1:04d}",
            from_team=from_team,
            to_team=to_team,
            kg_traded=kg,
            price_per_kg=self.INTERNAL_CARBON_PRICE_USD_PER_KG,
            reason=f"{from_team} has {self.budgets[from_team].surplus_kg:.1f}kg surplus; "
                   f"{to_team} is {abs(self.budgets[to_team].surplus_kg):.1f}kg over budget"
        )
        self.trades.append(trade)
        return trade

    def approve_trade(self, trade_id: str, approver: str = "governance"):
        for trade in self.trades:
            if trade.trade_id == trade_id:
                trade.status = "approved"
                trade.approved_by = approver
                self.budgets[trade.from_team].traded_kg -= trade.kg_traded
                self.budgets[trade.to_team].traded_kg += trade.kg_traded
                logger.info(f"Trade {trade_id} approved: {trade.kg_traded}kg from {trade.from_team} to {trade.to_team}")
                return trade
        raise ValueError(f"Trade {trade_id} not found")

    def to_dict(self) -> dict:
        return {
            "week": self.week,
            "budgets": {t: asdict(b) for t, b in self.budgets.items()},
            "trades": [asdict(t) for t in self.trades],
            "market_summary": {
                "total_teams": len(self.teams),
                "teams_in_surplus": len(self.find_surplus_teams()),
                "teams_in_deficit": len(self.find_deficit_teams()),
                "total_trades_proposed": len(self.trades),
                "total_trades_approved": sum(1 for t in self.trades if t.status == "approved"),
                "total_carbon_credits_usd": sum(b.carbon_credits for b in self.budgets.values())
            }
        }

    def save(self, path: str = "data/carbon_market.json"):
        Path(path).parent.mkdir(exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Carbon market state saved to {path}")
