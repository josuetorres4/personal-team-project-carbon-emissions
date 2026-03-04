"""
Environmental & Business Impact Calculator
===========================================
Translates raw kgCO₂e savings into meaningful environmental equivalencies
and business impact under carbon pricing scenarios.

Sources:
  - EPA Greenhouse Gas Equivalencies Calculator 2024
  - EU ETS price projections 2025/2030
  - EPA Social Cost of Carbon 2024
"""


# ── Equivalency factors (EPA 2024) ────────────────────────────────────

EQUIVALENCIES = [
    {
        "id": "miles_not_driven",
        "label": "Miles not driven",
        "unit": "miles",
        "kg_co2_per_unit": 0.404,
        "icon": "🚗",
    },
    {
        "id": "smartphones_charged",
        "label": "Smartphones charged",
        "unit": "charges",
        "kg_co2_per_unit": 0.008,
        "icon": "📱",
    },
    {
        "id": "led_bulb_hours",
        "label": "LED bulb hours",
        "unit": "hours",
        "kg_co2_per_unit": 0.005,
        "icon": "💡",
    },
    {
        "id": "tree_seedlings_10yr",
        "label": "Tree seedlings grown for 10 years",
        "unit": "trees",
        "kg_co2_per_unit": 60.0,
        "icon": "🌱",
    },
    {
        "id": "coal_not_burned",
        "label": "kg of coal not burned",
        "unit": "kg coal",
        "kg_co2_per_unit": 2.23,
        "icon": "⛏️",
    },
]

# ── Carbon pricing scenarios ──────────────────────────────────────────

CARBON_PRICE_SCENARIOS = [
    {"name": "Voluntary Market (current)", "usd_per_ton": 15.0},
    {"name": "EU ETS 2025",               "usd_per_ton": 75.0},
    {"name": "EU ETS 2030 (projected)",   "usd_per_ton": 150.0},
    {"name": "EPA Social Cost of Carbon", "usd_per_ton": 204.0},
]


def compute_equivalencies(kg_co2e: float, top_n: int = 3) -> list:
    """
    Convert a kgCO₂e value into human-readable environmental equivalencies.

    Returns the top_n most meaningful equivalencies (by absolute units).

    Args:
        kg_co2e: Carbon savings in kilograms of CO₂ equivalent (positive = savings)
        top_n: Number of equivalencies to return

    Returns:
        List of dicts with label, value, unit, icon
    """
    if kg_co2e <= 0:
        return []

    results = []
    for eq in EQUIVALENCIES:
        value = kg_co2e / eq["kg_co2_per_unit"]
        results.append({
            "id": eq["id"],
            "label": eq["label"],
            "value": round(value, 1),
            "unit": eq["unit"],
            "icon": eq["icon"],
        })

    # Sort by value descending so the most tangible numbers surface first
    results.sort(key=lambda x: x["value"], reverse=True)
    return results[:top_n]


def compute_business_impact(
    kg_co2e_saved: float,
    cost_change_usd: float,
    total_cloud_spend: float,
    annualize_factor: int = 12,
) -> dict:
    """
    Full business impact report for a carbon reduction achievement.

    Args:
        kg_co2e_saved: Monthly carbon savings in kg (positive = savings)
        cost_change_usd: Monthly cost change in USD (negative = savings, positive = increase)
        total_cloud_spend: Total monthly cloud spend in USD (baseline)
        annualize_factor: Months to multiply for annualized figures (default 12)

    Returns:
        Dict with equivalencies, pricing scenarios, efficiency metrics
    """
    tons_saved = kg_co2e_saved / 1000.0
    annual_kg_saved = kg_co2e_saved * annualize_factor
    annual_tons_saved = annual_kg_saved / 1000.0
    annual_cost_change = cost_change_usd * annualize_factor

    # Carbon pricing scenarios
    pricing = []
    for scenario in CARBON_PRICE_SCENARIOS:
        monthly_value = tons_saved * scenario["usd_per_ton"]
        annual_value = annual_tons_saved * scenario["usd_per_ton"]
        pricing.append({
            "scenario": scenario["name"],
            "usd_per_ton": scenario["usd_per_ton"],
            "monthly_value_usd": round(monthly_value, 2),
            "annual_value_usd": round(annual_value, 2),
        })

    # Efficiency metrics
    if cost_change_usd > 0 and kg_co2e_saved > 0:
        kg_per_dollar = round(kg_co2e_saved / cost_change_usd, 4)
    else:
        kg_per_dollar = None

    # Break-even: at what $/ton CO₂ does the optimization pay for itself?
    if tons_saved > 0 and cost_change_usd > 0:
        break_even_price = round(cost_change_usd / tons_saved, 2)
    else:
        break_even_price = None

    # Cost as percentage of cloud spend
    cost_pct = round((cost_change_usd / total_cloud_spend * 100), 4) if total_cloud_spend > 0 else 0.0

    return {
        "monthly": {
            "kg_co2e_saved": round(kg_co2e_saved, 4),
            "tons_co2e_saved": round(tons_saved, 6),
            "cost_change_usd": round(cost_change_usd, 2),
            "cost_change_pct": cost_pct,
        },
        "annual_projection": {
            "kg_co2e_saved": round(annual_kg_saved, 4),
            "tons_co2e_saved": round(annual_tons_saved, 6),
            "cost_change_usd": round(annual_cost_change, 2),
        },
        "equivalencies": compute_equivalencies(kg_co2e_saved),
        "carbon_pricing_scenarios": pricing,
        "efficiency": {
            "kg_co2e_per_dollar_extra_cost": kg_per_dollar,
            "break_even_carbon_price_usd_per_ton": break_even_price,
        },
    }
