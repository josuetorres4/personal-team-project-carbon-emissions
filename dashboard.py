"""
sust-AI-naible Dashboard
========================
Streamlit dashboard for visualizing the multi-agent carbon optimization system.

Run: streamlit run dashboard.py
Requires: run `python run_pipeline.py` first to generate data.
"""

import json
import os
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from src.agents.base import LLMProvider

# ── Page config ───────────────────────────────────────────────────────
st.set_page_config(
    page_title="sust-AI-naible",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Load data ─────────────────────────────────────────────────────────
DATA_DIR = "data"


@st.cache_data
def load_data():
    """Load all pipeline outputs."""
    data = {}
    try:
        data["baseline"] = pd.read_csv(f"{DATA_DIR}/jobs_baseline.csv")
        data["optimized"] = pd.read_csv(f"{DATA_DIR}/jobs_optimized.csv")
        data["intensity"] = pd.read_csv(f"{DATA_DIR}/carbon_intensity.csv")
        data["recommendations"] = pd.read_csv(f"{DATA_DIR}/recommendations.csv")
        data["governance"] = pd.read_csv(f"{DATA_DIR}/governance_decisions.csv")
        data["executions"] = pd.read_csv(f"{DATA_DIR}/executions.csv")
        data["verifications"] = pd.read_csv(f"{DATA_DIR}/verifications.csv")
        data["points"] = pd.read_csv(f"{DATA_DIR}/points.csv")
        data["leaderboard"] = pd.read_csv(f"{DATA_DIR}/leaderboard.csv")

        with open(f"{DATA_DIR}/pipeline_summary.json") as f:
            data["summary"] = json.load(f)

        with open(f"{DATA_DIR}/evidence_chains.json") as f:
            data["evidence"] = json.load(f)

        # Load agent traces if available
        traces_path = f"{DATA_DIR}/agent_traces.json"
        if os.path.exists(traces_path):
            with open(traces_path) as f:
                data["agent_traces"] = json.load(f)
        else:
            data["agent_traces"] = {}

    except FileNotFoundError as e:
        st.error(f"Data not found: {e}\n\nRun `python run_pipeline.py` first to generate data.")
        st.stop()

    return data


data = load_data()
summary = data["summary"]

# ── Sidebar ───────────────────────────────────────────────────────────
with st.sidebar:
    st.title("sust-AI-naible")
    st.caption("Multi-Agent Cloud Carbon Optimization")
    st.divider()

    st.metric("Simulation Days", summary["simulation_days"])
    st.metric("Total Jobs", f"{summary['total_jobs']:,}")
    st.metric("Carbon Price", "$75/ton CO₂e")

    st.divider()
    page = st.radio("Navigation", [
        "🌍 Your Impact This Week",
        "Overview",
        "Carbon Analysis",
        "Optimization Results",
        "Verification (MRV)",
        "Team Leaderboard",
        "Evidence Explorer",
        "Trade-off Analysis",
        "Agent Reasoning",
        "🤖 The Debate",
        "🌍 The Impact",
        "💬 Ask the Agent",
    ])

# Equivalency calculations for impact page
def carbon_to_equivalencies(kg: float) -> dict:
    return {
        "miles_not_driven": round(kg * 2.47, 1),          # EPA: 0.404 kgCO2/mile
        "phones_charged": round(kg * 121.6, 0),            # EPA: 0.00822 kg/charge
        "trees_for_a_year": round(kg / 21.77, 2),          # EPA: 21.77 kg/tree/year
        "coal_not_burned_grams": round(kg * 1000 / 2.42, 0),
        "hours_of_netflix": round(kg / 0.036, 1),          # 36g CO2/hour streaming
        "flights_avoided_minutes": round(kg / 0.255, 1),   # 255g CO2/passenger-mile, ~6mi/min
    }


# ══════════════════════════════════════════════════════════════════════
# PAGE: Your Impact This Week
# ══════════════════════════════════════════════════════════════════════
if page == "🌍 Your Impact This Week":
    st.title("🌍 What You Actually Did for the Planet")

    # Load proof-of-impact data if available
    poi_path = f"{DATA_DIR}/proof_of_impact.json"
    if os.path.exists(poi_path):
        with open(poi_path) as f:
            poi = json.load(f)

        total_kg = sum(p.get("carbon_saving_kg", 0) for p in poi if p.get("saving_is_significant"))
        eq = carbon_to_equivalencies(total_kg)

        # Hero metric — big, emotional, clear
        st.markdown(f"""
        <div style="text-align: center; padding: 2rem; background: linear-gradient(135deg, #1a5e1a, #2d8f2d); border-radius: 1rem; margin-bottom: 2rem;">
            <h1 style="color: white; font-size: 3rem; margin: 0;">{total_kg:.1f} kg CO₂e</h1>
            <p style="color: #b8e6b8; font-size: 1.2rem;">Verified carbon saved this period</p>
        </div>
        """, unsafe_allow_html=True)

        # Real-world equivalencies
        col1, col2, col3 = st.columns(3)
        col1.metric("🚗 Miles not driven", f"{eq['miles_not_driven']:,}")
        col2.metric("📱 Phones charged", f"{int(eq['phones_charged']):,}")
        col3.metric("🌳 Trees working for a year", f"{eq['trees_for_a_year']}")

        col4, col5 = st.columns(2)
        col4.metric("🏭 Coal not burned", f"{int(eq['coal_not_burned_grams']):,}g")
        col5.metric("✈️ Flight time avoided", f"{eq['flights_avoided_minutes']:.0f} min")

        # CSRD readiness indicator
        st.subheader("📋 CSRD Filing Readiness")
        significant_count = sum(1 for p in poi if p.get("saving_is_significant"))
        real_data_count = sum(1 for p in poi if p.get("is_real_data"))

        st.progress(significant_count / max(len(poi), 1),
                    text=f"{significant_count}/{len(poi)} savings are audit-ready")

        if real_data_count == len(poi) and len(poi) > 0:
            st.success("✅ All savings computed from real grid data — suitable for CSRD Scope 2 disclosure")
        elif len(poi) > 0:
            st.warning(f"⚠️ {len(poi)-real_data_count} savings use synthetic data — not suitable for regulatory filing")

        # Carbon market summary
        market_path = f"{DATA_DIR}/carbon_market.json"
        if os.path.exists(market_path):
            with open(market_path) as f:
                market_data = json.load(f)
            st.subheader("💱 Carbon Market Summary")
            ms = market_data.get("market_summary", {})
            col6, col7, col8 = st.columns(3)
            col6.metric("Teams", ms.get("total_teams", 0))
            col7.metric("Trades Approved", ms.get("total_trades_approved", 0))
            col8.metric("Carbon Credits (USD)", f"${ms.get('total_carbon_credits_usd', 0):.2f}")

        # Download evidence
        from pathlib import Path as _Path
        evidence_dir = _Path("data/evidence_cards")
        if evidence_dir.exists() and list(evidence_dir.glob("*.pdf")):
            if st.button("📥 Download All Evidence Cards (ZIP)"):
                import zipfile
                import io
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w") as z:
                    for pdf in evidence_dir.glob("*.pdf"):
                        z.write(pdf, pdf.name)
                st.download_button("Download ZIP", buf.getvalue(), "evidence_cards.zip")
    else:
        st.info("No proof-of-impact data available yet. Run `python run_pipeline.py` first.")


# ══════════════════════════════════════════════════════════════════════
# PAGE: Overview
# ══════════════════════════════════════════════════════════════════════
if page == "Overview":
    st.title("System Overview")
    st.markdown("**Closed-loop carbon optimization**: Sense → Model → Decide → Act → Verify → Learn")

    # Key metrics
    col1, col2, col3, col4 = st.columns(4)

    baseline_e = summary["baseline"]["total_emissions_kgco2e"]
    optimized_e = summary["optimized"]["total_emissions_kgco2e"]
    reduction = summary["improvement"]["emissions_reduction_kgco2e"]
    reduction_pct = summary["improvement"]["emissions_reduction_pct"]

    col1.metric(
        "Baseline Emissions",
        f"{baseline_e:.1f} kgCO₂e",
    )
    col2.metric(
        "Optimized Emissions",
        f"{optimized_e:.1f} kgCO₂e",
        delta=f"-{reduction:.1f} kgCO₂e",
        delta_color="inverse",
    )
    col3.metric(
        "Reduction",
        f"{reduction_pct:.1f}%",
    )
    col4.metric(
        "Verified Savings",
        f"{summary['pipeline']['verification_summary']['total_verified_savings_kgco2e']*1000:.0f} gCO₂e",
    )

    st.divider()

    # Pipeline flow
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Recommendations", summary["pipeline"]["recommendations_generated"])
    col2.metric("Approved", summary["pipeline"]["recommendations_approved"])
    col3.metric("Executed", summary["pipeline"]["recommendations_executed"])
    col4.metric("Verified", summary["pipeline"]["verifications_completed"])
    col5.metric("Points Awarded", f"{summary['gamification']['total_points_awarded']:,}")

    # Cost comparison
    st.divider()
    st.subheader("Cost Comparison")
    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Baseline Cloud Cost",
        f"${summary['baseline']['total_cost_usd']:,.2f}",
    )
    col2.metric(
        "Optimized Cloud Cost",
        f"${summary['optimized']['total_cost_usd']:,.2f}",
        delta=f"${summary['improvement']['cost_change_usd']:+,.2f}",
        delta_color="inverse",
    )
    col3.metric(
        "Baseline Effective Cost",
        f"${summary['baseline']['effective_cost_usd']:,.2f}",
        help="Cloud cost + (emissions × $75/ton)",
    )

    # Verification status breakdown
    st.divider()
    st.subheader("Verification Status")
    v_status = summary["pipeline"]["verification_summary"].get("by_status", {})
    if v_status:
        status_df = pd.DataFrame([
            {"Status": k.title(), "Count": v} for k, v in v_status.items()
        ])
        fig = px.pie(status_df, values="Count", names="Status",
                     color="Status",
                     color_discrete_map={
                         "Confirmed": "#2ecc71",
                         "Partial": "#f39c12",
                         "Refuted": "#e74c3c",
                         "Inconclusive": "#95a5a6",
                     })
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════
# PAGE: Carbon Analysis
# ══════════════════════════════════════════════════════════════════════
elif page == "Carbon Analysis":
    st.title("Carbon Emissions Analysis")

    baseline = data["baseline"]
    baseline["started_at"] = pd.to_datetime(baseline["started_at"])

    # Emissions by region
    st.subheader("Emissions by Region (Baseline)")
    by_region = baseline.groupby("region").agg(
        total_kgco2e=("kgco2e", "sum"),
        total_jobs=("job_id", "count"),
        total_cost=("cost_usd", "sum"),
    ).reset_index()

    fig = px.bar(by_region, x="region", y="total_kgco2e",
                 color="region", text_auto=".1f",
                 labels={"total_kgco2e": "Total kgCO₂e", "region": "Region"},
                 title="Baseline Emissions by Region")
    fig.update_layout(showlegend=False, height=400)
    st.plotly_chart(fig, use_container_width=True)

    # Emissions by workload type
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("By Workload Type")
        by_type = baseline.groupby("workload_type")["kgco2e"].sum().reset_index()
        fig = px.pie(by_type, values="kgco2e", names="workload_type",
                     title="Emissions Share by Workload Type")
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("By Category (Flexibility)")
        by_cat = baseline.groupby("category")["kgco2e"].sum().reset_index()
        fig = px.pie(by_cat, values="kgco2e", names="category",
                     title="Emissions Share by Category",
                     color="category",
                     color_discrete_map={
                         "urgent": "#e74c3c",
                         "balanced": "#f39c12",
                         "sustainable": "#2ecc71",
                     })
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)

    # Grid carbon intensity heatmap
    st.subheader("Grid Carbon Intensity Over Time")
    intensity = data["intensity"].copy()
    intensity["timestamp"] = pd.to_datetime(intensity["timestamp"])
    intensity["hour"] = intensity["timestamp"].dt.hour
    intensity["day"] = intensity["timestamp"].dt.date

    selected_region = st.selectbox("Select Region", intensity["region"].unique())
    region_data = intensity[intensity["region"] == selected_region]
    pivot = region_data.pivot_table(
        index="hour", columns="day", values="intensity_gco2_kwh", aggfunc="mean"
    )
    fig = px.imshow(pivot, labels=dict(x="Day", y="Hour (UTC)", color="gCO₂/kWh"),
                    title=f"Carbon Intensity Heatmap — {selected_region}",
                    color_continuous_scale="RdYlGn_r", aspect="auto")
    fig.update_layout(height=400)
    st.plotly_chart(fig, use_container_width=True)

    # Daily emissions trend
    st.subheader("Daily Emissions Trend (Baseline)")
    baseline["date"] = baseline["started_at"].dt.date
    daily = baseline.groupby("date")["kgco2e"].sum().reset_index()
    fig = px.line(daily, x="date", y="kgco2e",
                  labels={"kgco2e": "kgCO₂e", "date": "Date"},
                  title="Daily Total Emissions")
    fig.update_layout(height=350)
    st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════
# PAGE: Optimization Results
# ══════════════════════════════════════════════════════════════════════
elif page == "Optimization Results":
    st.title("Optimization Results")

    recs = data["recommendations"]
    gov = data["governance"]

    # Recommendations overview
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Recommendations", len(recs))
    col2.metric("Approved", len(gov[gov["decision"] == "approved"]))
    col3.metric("Rejected", len(gov[gov["decision"] == "rejected"]))

    # Governance decisions
    st.subheader("Governance Decisions by Risk Level")
    if not gov.empty:
        gov_pivot = gov.groupby(["final_risk_level", "decision"]).size().reset_index(name="count")
        fig = px.bar(gov_pivot, x="final_risk_level", y="count", color="decision",
                     barmode="group",
                     color_discrete_map={"approved": "#2ecc71", "rejected": "#e74c3c"},
                     labels={"count": "Count", "final_risk_level": "Risk Level"})
        fig.update_layout(height=350)
        st.plotly_chart(fig, use_container_width=True)

    # Region shift patterns
    st.subheader("Region Shift Patterns")
    if not recs.empty:
        shifts = recs.groupby(["current_region", "proposed_region"]).size().reset_index(name="count")
        shifts = shifts[shifts["current_region"] != shifts["proposed_region"]]
        if not shifts.empty:
            fig = px.sunburst(shifts, path=["current_region", "proposed_region"], values="count",
                              title="Where Jobs Moved: From → To")
            fig.update_layout(height=500)
            st.plotly_chart(fig, use_container_width=True)

    # Carbon savings distribution
    st.subheader("Estimated Carbon Savings Distribution")
    if not recs.empty:
        fig = px.histogram(recs, x="est_carbon_delta_kg",
                           nbins=50, labels={"est_carbon_delta_kg": "Estimated Carbon Delta (kgCO₂e)"},
                           title="Distribution of Estimated Carbon Deltas per Recommendation")
        fig.add_vline(x=0, line_dash="dash", line_color="red")
        fig.update_layout(height=350)
        st.plotly_chart(fig, use_container_width=True)

    # Recommendations table
    st.subheader("Recommendation Details")
    if not recs.empty:
        display_cols = ["recommendation_id", "action_type", "current_region", "proposed_region",
                        "est_carbon_delta_kg", "est_cost_delta_usd", "confidence", "risk_level", "status"]
        st.dataframe(
            recs[display_cols].sort_values("est_carbon_delta_kg").head(50),
            use_container_width=True,
            height=400,
        )


# ══════════════════════════════════════════════════════════════════════
# PAGE: Verification (MRV)
# ══════════════════════════════════════════════════════════════════════
elif page == "Verification (MRV)":
    st.title("Verification — Measurement, Reporting, Verification")
    st.markdown("""
    Every claimed carbon reduction is verified against a **counterfactual baseline**:
    *"What would emissions have been if we hadn't made the change?"*
    
    This is the core differentiator — auditable proof, not estimates.
    """)

    verify = data["verifications"]

    if verify.empty:
        st.warning("No verification data available.")
    else:
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Verified Records", len(verify))
        col2.metric("Total Verified Savings",
                     f"{verify['verified_savings_kgco2e'].sum()*1000:.0f} gCO₂e")
        confirmed = len(verify[verify["verification_status"] == "confirmed"])
        col3.metric("Confirmed", f"{confirmed} ({confirmed/len(verify)*100:.0f}%)")
        col4.metric("SLA Violations",
                     f"{(~verify['sla_compliant']).sum()}")

        # Savings with confidence intervals
        st.subheader("Verified Savings with 90% Confidence Intervals")

        # Take top 30 by savings for readable chart
        top_verify = verify.nlargest(30, "verified_savings_kgco2e").copy()
        top_verify["index"] = range(len(top_verify))
        top_verify["savings_g"] = top_verify["verified_savings_kgco2e"] * 1000
        top_verify["ci_lower_g"] = top_verify["ci_lower"] * 1000
        top_verify["ci_upper_g"] = top_verify["ci_upper"] * 1000

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=top_verify["index"],
            y=top_verify["savings_g"],
            name="Verified Savings",
            marker_color=top_verify["verification_status"].map({
                "confirmed": "#2ecc71",
                "partial": "#f39c12",
                "refuted": "#e74c3c",
                "inconclusive": "#95a5a6",
            }),
        ))
        fig.add_trace(go.Scatter(
            x=top_verify["index"],
            y=top_verify["ci_upper_g"],
            mode="markers",
            marker=dict(symbol="line-ns-open", size=10, color="gray"),
            name="90% CI Upper",
        ))
        fig.add_trace(go.Scatter(
            x=top_verify["index"],
            y=top_verify["ci_lower_g"],
            mode="markers",
            marker=dict(symbol="line-ns-open", size=10, color="gray"),
            name="90% CI Lower",
        ))
        fig.add_hline(y=0, line_dash="dash", line_color="red")
        fig.update_layout(
            title="Top 30 Verified Savings (gCO₂e) with Confidence Intervals",
            xaxis_title="Recommendation (ranked)",
            yaxis_title="gCO₂e Saved",
            height=450,
            showlegend=True,
        )
        st.plotly_chart(fig, use_container_width=True)

        # Counterfactual vs actual scatter
        st.subheader("Counterfactual vs Actual Emissions")
        fig = px.scatter(verify,
                         x="counterfactual_kgco2e",
                         y="actual_kgco2e",
                         color="verification_status",
                         color_discrete_map={
                             "confirmed": "#2ecc71",
                             "partial": "#f39c12",
                             "refuted": "#e74c3c",
                         },
                         labels={
                             "counterfactual_kgco2e": "Counterfactual (kgCO₂e)",
                             "actual_kgco2e": "Actual (kgCO₂e)",
                         },
                         title="Counterfactual vs Actual: Points below diagonal = real savings")
        # Add y=x line
        max_val = max(verify["counterfactual_kgco2e"].max(), verify["actual_kgco2e"].max())
        fig.add_shape(type="line", x0=0, y0=0, x1=max_val, y1=max_val,
                      line=dict(dash="dash", color="gray"))
        fig.update_layout(height=450)
        st.plotly_chart(fig, use_container_width=True)

        # Verification status breakdown
        st.subheader("Verification Status Breakdown")
        status_counts = verify["verification_status"].value_counts().reset_index()
        status_counts.columns = ["Status", "Count"]
        fig = px.bar(status_counts, x="Status", y="Count", color="Status",
                     color_discrete_map={
                         "confirmed": "#2ecc71",
                         "partial": "#f39c12",
                         "refuted": "#e74c3c",
                         "inconclusive": "#95a5a6",
                     })
        fig.update_layout(height=300, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════
# PAGE: Team Leaderboard
# ══════════════════════════════════════════════════════════════════════
elif page == "Team Leaderboard":
    st.title("Team Leaderboard")
    st.markdown("Points are awarded **only** for verified carbon savings. No points for unverified claims.")

    lb = data["leaderboard"]

    if lb.empty:
        st.warning("No leaderboard data available.")
    else:
        # Podium
        if len(lb) >= 3:
            col1, col2, col3 = st.columns(3)
            col2.metric(
                f"#1 {lb.iloc[0]['team_id']}",
                f"{int(lb.iloc[0]['total_points']):,} pts",
                f"{lb.iloc[0]['total_kgco2e_saved']*1000:.0f} gCO₂e saved",
            )
            col1.metric(
                f"#2 {lb.iloc[1]['team_id']}",
                f"{int(lb.iloc[1]['total_points']):,} pts",
                f"{lb.iloc[1]['total_kgco2e_saved']*1000:.0f} gCO₂e saved",
            )
            col3.metric(
                f"#3 {lb.iloc[2]['team_id']}",
                f"{int(lb.iloc[2]['total_points']):,} pts",
                f"{lb.iloc[2]['total_kgco2e_saved']*1000:.0f} gCO₂e saved",
            )

        st.divider()

        # Full leaderboard bar chart
        fig = px.bar(lb, x="team_id", y="total_points",
                     color="total_kgco2e_saved",
                     color_continuous_scale="Greens",
                     text="total_points",
                     labels={"total_points": "Points", "team_id": "Team",
                             "total_kgco2e_saved": "kgCO₂e Saved"})
        fig.update_layout(height=400, title="Team Points (based on verified savings)")
        st.plotly_chart(fig, use_container_width=True)

        # Points breakdown
        points = data["points"]
        if not points.empty:
            st.subheader("Points Activity Log")
            st.dataframe(
                points[["team_id", "points", "kgco2e_saved", "reason"]].sort_values("points", ascending=False),
                use_container_width=True,
                height=400,
            )


# ══════════════════════════════════════════════════════════════════════
# PAGE: Evidence Explorer
# ══════════════════════════════════════════════════════════════════════
elif page == "Evidence Explorer":
    st.title("Evidence Chain Explorer")
    st.markdown("""
    Every verified carbon reduction has a **machine-readable evidence chain** — 
    an auditable trace from raw data through computation to final claim.
    This is the MRV (Measurement, Reporting, Verification) standard.
    """)

    evidence = data["evidence"]

    if not evidence:
        st.warning("No evidence data available.")
    else:
        # Select a verification record
        options = {f"{e['recommendation_id']} — {e['verification_status']} — "
                   f"{e['verified_savings_kgco2e']*1000:.1f} gCO₂e": i
                   for i, e in enumerate(evidence)}

        selected = st.selectbox("Select a verification record:", list(options.keys()))
        idx = options[selected]
        record = evidence[idx]

        # Summary
        col1, col2, col3 = st.columns(3)
        col1.metric("Verified Savings", f"{record['verified_savings_kgco2e']*1000:.2f} gCO₂e")
        col2.metric("90% CI",
                     f"[{record['ci_lower']*1000:.2f}, {record['ci_upper']*1000:.2f}] gCO₂e")
        col3.metric("Status", record["verification_status"].upper())

        st.divider()

        # Evidence chain steps
        st.subheader("Evidence Chain")
        for i, step in enumerate(record["evidence_chain"]):
            with st.expander(f"Step {i+1}: {step['step']}", expanded=(i < 2)):
                st.markdown(f"**{step['description']}**")
                if "data" in step:
                    st.json(step["data"])

        # Raw JSON
        with st.expander("Raw JSON (machine-readable)"):
            st.json(record)


# ══════════════════════════════════════════════════════════════════════
# PAGE: Trade-off Analysis
# ══════════════════════════════════════════════════════════════════════
elif page == "Trade-off Analysis":
    st.title("Trade-off Analysis: Carbon vs Cost")
    st.markdown("""
    How does the internal carbon price affect optimization decisions?
    Higher carbon prices → more aggressive optimization → more savings but potentially higher cloud costs.
    """)

    # Carbon price sensitivity analysis
    st.subheader("Carbon Price Sensitivity")

    baseline = data["baseline"]
    total_baseline_emissions = baseline["kgco2e"].sum()
    total_baseline_cost = baseline["cost_usd"].sum()

    # Simulate different carbon prices
    recs = data["recommendations"]
    if not recs.empty:
        carbon_prices = [0, 25, 50, 75, 100, 150, 200, 300, 500]
        sensitivity_data = []

        for cp in carbon_prices:
            # At higher carbon prices, more recommendations become worthwhile
            # Simulate by filtering recs where carbon savings × price > cost increase
            qualifying = recs[
                (recs["est_carbon_delta_kg"].abs() * cp / 1000) > recs["est_cost_delta_usd"].clip(lower=0)
            ]
            est_carbon_saved = qualifying["est_carbon_delta_kg"].sum() * -1  # flip sign
            est_cost_increase = qualifying["est_cost_delta_usd"].sum()

            effective_cost_baseline = total_baseline_cost + total_baseline_emissions / 1000 * cp
            effective_cost_optimized = (
                total_baseline_cost + est_cost_increase +
                (total_baseline_emissions - est_carbon_saved) / 1000 * cp
            )

            sensitivity_data.append({
                "Carbon Price ($/ton)": cp,
                "Qualifying Recs": len(qualifying),
                "Est. kgCO₂e Saved": round(est_carbon_saved, 2),
                "Est. Cost Change ($)": round(est_cost_increase, 2),
                "Effective Cost Baseline ($)": round(effective_cost_baseline, 2),
                "Effective Cost Optimized ($)": round(effective_cost_optimized, 2),
            })

        sens_df = pd.DataFrame(sensitivity_data)

        # Pareto chart
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(
            go.Scatter(x=sens_df["Carbon Price ($/ton)"],
                       y=sens_df["Est. kgCO₂e Saved"],
                       name="kgCO₂e Saved",
                       mode="lines+markers",
                       line=dict(color="#2ecc71", width=3)),
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(x=sens_df["Carbon Price ($/ton)"],
                       y=sens_df["Est. Cost Change ($)"],
                       name="Cost Change ($)",
                       mode="lines+markers",
                       line=dict(color="#e74c3c", width=3)),
            secondary_y=True,
        )
        fig.add_vline(x=75, line_dash="dash", line_color="gray",
                      annotation_text="Current: $75/ton")
        fig.update_xaxes(title_text="Internal Carbon Price ($/ton)")
        fig.update_yaxes(title_text="kgCO₂e Saved", secondary_y=False)
        fig.update_yaxes(title_text="Cost Change ($)", secondary_y=True)
        fig.update_layout(height=450, title="Carbon Price Sensitivity: Savings vs Cost Trade-off")
        st.plotly_chart(fig, use_container_width=True)

        # Data table
        st.dataframe(sens_df, use_container_width=True)

    # Baseline vs Optimized comparison
    st.subheader("Baseline vs Optimized: Region Distribution")
    baseline_regions = data["baseline"].groupby("region")["kgco2e"].sum().reset_index()
    baseline_regions["scenario"] = "Baseline"
    optimized_regions = data["optimized"].groupby("region")["kgco2e"].sum().reset_index()
    optimized_regions["scenario"] = "Optimized"
    comparison = pd.concat([baseline_regions, optimized_regions])

    fig = px.bar(comparison, x="region", y="kgco2e", color="scenario",
                 barmode="group",
                 color_discrete_map={"Baseline": "#e74c3c", "Optimized": "#2ecc71"},
                 labels={"kgco2e": "kgCO₂e", "region": "Region"},
                 title="Emissions by Region: Before vs After Optimization")
    fig.update_layout(height=400)
    st.plotly_chart(fig, use_container_width=True)

    # AI vs Deterministic explainer
    st.divider()
    st.subheader("AI vs Deterministic Boundaries")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### LLM-Driven (Soft, Advisory)")
        st.markdown("""
        - Parsing organizational policies into rules
        - Generating ticket/PR descriptions
        - Explaining recommendations in plain language
        - Summarizing verification reports
        - Developer nudges and contextual tips
        """)

    with col2:
        st.markdown("### Deterministic (Hard, Authoritative)")
        st.markdown("""
        - Emissions calculations (kgCO₂e = f(resource, grid, PUE))
        - Optimization solver (scoring, constraint checks)
        - Cost calculations
        - Counterfactual verification
        - Points computation
        - SLA compliance checks
        """)

    st.info("**Why this boundary?** Every number that appears in a verification record "
            "must be reproducible. An auditor should never encounter 'the LLM said 42.7 kgCO₂e.' "
            "LLMs translate at the edges; deterministic systems compute in the core.")


# ══════════════════════════════════════════════════════════════════════
# PAGE: Agent Reasoning
# ══════════════════════════════════════════════════════════════════════
elif page == "Agent Reasoning":
    st.title("Agent Reasoning Traces")
    st.markdown("""
    Each agent in the system maintains a **reasoning trace** — a log of its LLM 
    reasoning steps and tool calls. This is what makes them *agents*, not just functions:
    they reason about their tasks, use tools, and produce auditable thought processes.
    """)

    traces = data.get("agent_traces", {})
    if not traces:
        st.warning("No agent traces available. Run `python run_pipeline.py` to generate them.")
    else:
        # Agent summary
        st.subheader("Agent Activity Summary")
        agent_stats = summary.get("agents", {})
        if agent_stats:
            cols = st.columns(len(agent_stats))
            for i, (agent_name, stats) in enumerate(agent_stats.items()):
                with cols[i]:
                    st.metric(agent_name.title(), f"{stats['reasoning_steps']} reasoning steps")
                    st.caption(f"{stats['actions_taken']} tool calls")

        st.divider()

        # LLM Provider info
        llm_provider = summary.get("llm_provider", "unknown")
        if llm_provider == "mock":
            st.info("**LLM Mode: Mock** — The system ran with a deterministic mock LLM. "
                    "To use a real LLM, set `OPENAI_API_KEY` and re-run the pipeline. "
                    "The mock produces structured, contextually appropriate responses "
                    "for development and demo purposes.")
        else:
            st.success(f"**LLM Mode: {llm_provider}** — The system used a real LLM for reasoning.")

        # Per-agent trace viewer
        st.subheader("Agent Trace Explorer")
        selected_agent = st.selectbox("Select Agent", list(traces.keys()))

        if selected_agent:
            trace = traces[selected_agent]
            st.markdown(f"**Agent:** {trace.get('agent', selected_agent)}")
            st.markdown(f"**Purpose:** {trace.get('purpose', 'N/A')}")

            memory = trace.get("memory", {})

            # Reasoning steps
            reasoning = memory.get("reasoning_trace", [])
            if reasoning:
                st.subheader(f"Reasoning Steps ({len(reasoning)})")
                for i, step in enumerate(reasoning):
                    with st.expander(f"Step {i+1}: {step.get('step', 'unknown')}", expanded=(i == 0)):
                        st.markdown(f"**{step.get('step', '')}**")
                        st.text(step.get("content", ""))
                        st.caption(f"Timestamp: {step.get('timestamp', 'N/A')}")

            # Tool calls
            actions = memory.get("actions_taken", [])
            if actions:
                st.subheader(f"Tool Calls ({len(actions)})")
                for i, action in enumerate(actions[:20]):  # Show first 20
                    with st.expander(f"Tool: {action.get('tool', 'unknown')}"):
                        st.json(action.get("inputs", {}))
                        st.text(f"Output: {action.get('output', 'N/A')[:300]}")

        # Architecture diagram
        st.divider()
        st.subheader("Agent Architecture")
        st.markdown("""
        ```
        ┌─────────────────────────────────────────────────────────────┐
        │                      ORCHESTRATOR                           │
        │   Manages agent lifecycle, message passing, trace collection│
        ├─────────────────────────────────────────────────────────────┤
        │                                                             │
        │  ┌──────────────┐   LLM reasoning                          │
        │  │ Planner      │──→ Generates rationales for recs          │
        │  │ Agent        │   Deterministic: scoring, constraints     │
        │  └──────┬───────┘                                           │
        │         │ recommendations                                   │
        │         ▼                                                   │
        │  ┌──────────────┐   LLM reasoning                          │
        │  │ Governance   │──→ Contextual risk assessment             │
        │  │ Agent        │   Deterministic: threshold rules          │
        │  └──────┬───────┘                                           │
        │         │ approved recs                                     │
        │         ▼                                                   │
        │  ┌──────────────┐   LLM reasoning                          │
        │  │ Executor     │──→ Generates ticket/PR content            │
        │  │ Agent        │   Deterministic: config changes           │
        │  └──────┬───────┘                                           │
        │         │ executed changes                                   │
        │         ▼                                                   │
        │  ┌──────────────┐   NO LLM — fully deterministic            │
        │  │ Verifier     │   Counterfactual math + evidence chains   │
        │  └──────┬───────┘                                           │
        │         │ verified outcomes                                  │
        │         ▼                                                   │
        │  ┌──────────────┐   LLM reasoning                          │
        │  │ Developer    │──→ Team summaries, nudges                 │
        │  │ Copilot      │   Deterministic: points calculation       │
        │  └──────────────┘                                           │
        └─────────────────────────────────────────────────────────────┘
        ```
        
        **Key insight**: The LLM reasons about *what to say* and *how to explain*. 
        The deterministic code computes *what the numbers are*. This separation means 
        every number is auditable, and every explanation is contextual.
        """)

# ══════════════════════════════════════════════════════════════════════
# PAGE: The Debate — Multi-Agent Dialogue Viewer
# ══════════════════════════════════════════════════════════════════════
elif page == "🤖 The Debate":
    st.title("🤖 The Debate")
    st.markdown(
        "Multi-agent negotiation between **Planner** and **Governance** agents. "
        "Each message was generated by an LLM reasoning in real-time about the batch strategy."
    )

    dialogues_path = f"{DATA_DIR}/agent_dialogues.json"
    if not os.path.exists(dialogues_path):
        st.info("No dialogue data found. Run `python run_pipeline.py` to generate it.")
    else:
        with open(dialogues_path) as _f:
            dialogues = json.load(_f)

        if not dialogues:
            st.info("No dialogues recorded in the last pipeline run.")
        else:
            # Color mapping by agent role
            AGENT_COLORS = {
                "planner": "#1a73e8",    # blue
                "governance": "#d93025",  # red
                "accountant": "#1e8e3e",  # green
            }

            def _agent_color(name: str) -> str:
                n = name.lower()
                for key, color in AGENT_COLORS.items():
                    if key in n:
                        return color
                return "#5f6368"

            for dialogue in dialogues:
                with st.expander(
                    f"📋 Dialogue: {dialogue.get('topic', 'Unknown')} "
                    f"— {dialogue.get('total_rounds', 0)} rounds, "
                    f"outcome: **{dialogue.get('outcome', 'unknown')}**",
                    expanded=True,
                ):
                    col_a, col_b, col_c = st.columns(3)
                    col_a.metric("Total Rounds", dialogue.get("total_rounds", 0))
                    col_b.metric("Total Messages", dialogue.get("total_messages", 0))
                    col_c.metric(
                        "Outcome",
                        dialogue.get("outcome", "unknown").replace("_", " ").title(),
                    )
                    st.divider()

                    for msg in dialogue.get("messages", []):
                        agent_name = msg.get("from", "Unknown")
                        color = _agent_color(agent_name)
                        msg_type = msg.get("type", "proposal").upper()
                        round_num = msg.get("round", 0)

                        st.markdown(
                            f"<div style='border-left: 4px solid {color}; padding: 8px 12px; "
                            f"margin: 8px 0; background-color: #f8f9fa; border-radius: 4px;'>"
                            f"<b style='color:{color}'>{agent_name}</b> "
                            f"<span style='font-size:0.8em; color:#666;'>"
                            f"[{msg_type}] Round {round_num}</span><br/>"
                            f"{msg.get('content', '')}"
                            f"</div>",
                            unsafe_allow_html=True,
                        )

                        structured = msg.get("data", {})
                        if structured:
                            with st.expander("📊 Structured Data"):
                                st.json(structured)

# ══════════════════════════════════════════════════════════════════════
# PAGE: The Impact — Environmental & Business Impact
# ══════════════════════════════════════════════════════════════════════
elif page == "🌍 The Impact":
    st.title("🌍 The Impact")
    st.markdown(
        "Translate carbon savings into real-world environmental equivalencies "
        "and business value under multiple carbon pricing scenarios."
    )

    impact = summary.get("impact", {})
    if not impact:
        st.info("No impact data found. Run `python run_pipeline.py` to generate it.")
    else:
        monthly = impact.get("monthly", {})
        annual = impact.get("annual_projection", {})
        efficiency = impact.get("efficiency", {})

        # ── Big metrics ───────────────────────────────────────────────
        st.subheader("Key Metrics")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric(
            "Monthly CO₂ Saved",
            f"{monthly.get('kg_co2e_saved', 0):.2f} kg",
            help="kgCO₂e reduced this simulation period",
        )
        col2.metric(
            "Annual Projection",
            f"{annual.get('kg_co2e_saved', 0):.2f} kg",
            help="Extrapolated over 12 months",
        )
        col3.metric(
            "Cost Change",
            f"${monthly.get('cost_change_usd', 0):+.2f}",
            delta=f"{monthly.get('cost_change_pct', 0):+.3f}%",
            delta_color="inverse",
        )
        col4.metric(
            "Tons CO₂ Saved",
            f"{monthly.get('tons_co2e_saved', 0):.4f} t",
        )

        st.divider()

        # ── Equivalencies ─────────────────────────────────────────────
        st.subheader("🌿 Environmental Equivalencies")
        equivalencies = impact.get("equivalencies", [])
        if equivalencies:
            eq_cols = st.columns(len(equivalencies))
            for col, eq in zip(eq_cols, equivalencies):
                col.metric(
                    f"{eq.get('icon', '')} {eq.get('label', '')}",
                    f"{eq.get('value', 0):,.1f} {eq.get('unit', '')}",
                )
        else:
            st.info("No equivalency data (savings may be zero or negative).")

        st.divider()

        # ── Carbon pricing scenarios ──────────────────────────────────
        st.subheader("�� Carbon Pricing Scenarios")
        pricing = impact.get("carbon_pricing_scenarios", [])
        if pricing:
            pricing_df = pd.DataFrame(pricing)
            pricing_df.columns = [
                "Scenario", "$/ton CO₂", "Monthly Value ($)", "Annual Value ($)"
            ]
            st.dataframe(pricing_df, use_container_width=True, hide_index=True)

            fig = px.bar(
                pricing_df,
                x="Scenario",
                y="Annual Value ($)",
                title="Annual Carbon Value by Pricing Scenario",
                color="Annual Value ($)",
                color_continuous_scale="Greens",
            )
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No pricing scenario data available.")

        st.divider()

        # ── Break-even analysis ───────────────────────────────────────
        st.subheader("📈 Break-Even Analysis")
        col_a, col_b = st.columns(2)
        be_price = efficiency.get("break_even_carbon_price_usd_per_ton")
        kg_per_dollar = efficiency.get("kg_co2e_per_dollar_extra_cost")

        if be_price is not None:
            col_a.metric(
                "Break-Even Carbon Price",
                f"${be_price:.2f}/ton",
                help="At this carbon price, the optimization pays for itself",
            )
        else:
            col_a.info("No cost increase — optimization is free!")

        if kg_per_dollar is not None:
            col_b.metric(
                "Efficiency",
                f"{kg_per_dollar:.4f} kg CO₂/$",
                help="kgCO₂e saved per dollar of additional cost",
            )
        else:
            col_b.info("No additional cost — zero cost optimization")

# ══════════════════════════════════════════════════════════════════════
# PAGE: Ask the Agent — Interactive Chat
# ══════════════════════════════════════════════════════════════════════
elif page == "💬 Ask the Agent":
    st.title("💬 Ask the Agent")
    st.caption(
        "Chat with the Carbon Optimization Assistant — ask about your pipeline results, "
        "the methodology, or carbon reduction strategies."
    )

    # LLM mode banner
    llm_provider = summary.get("llm_provider", "mock")
    if llm_provider == "mock":
        st.info(
            "🤖 **Demo mode** — responses are generated by the built-in mock LLM. "
            "Set `OPENAI_API_KEY` and re-run `python run_pipeline.py` for GPT-powered answers."
        )
    else:
        st.success(f"✅ **Live mode** — using {llm_provider} for responses.")

    # System prompt includes actual pipeline numbers so the LLM can reference them
    sys_prompt = (
        "You are the sust-AI-naible Carbon Optimization Assistant, an expert AI that helps "
        "engineering teams understand and reduce their cloud carbon footprint.\n\n"
        "Latest pipeline run context — reference these exact numbers when answering:\n"
        f"- Simulation: {summary['simulation_days']} days, {summary['total_jobs']:,} jobs\n"
        f"- Baseline emissions: {summary['baseline']['total_emissions_kgco2e']:.1f} kgCO₂e\n"
        f"- Optimized emissions: {summary['optimized']['total_emissions_kgco2e']:.1f} kgCO₂e\n"
        f"- Reduction: {summary['improvement']['emissions_reduction_pct']:.1f}% "
        f"({summary['improvement']['emissions_reduction_kgco2e']:.1f} kgCO₂e)\n"
        f"- Recommendations: {summary['pipeline']['recommendations_generated']:,} generated, "
        f"{summary['pipeline']['recommendations_approved']:,} approved\n"
        f"- Executed: {summary['pipeline']['recommendations_executed']:,}, "
        f"Verified: {summary['pipeline']['verifications_completed']:,}\n"
        f"- Baseline cost: ${summary['baseline']['total_cost_usd']:,.2f} → "
        f"Optimized: ${summary['optimized']['total_cost_usd']:,.2f} "
        f"(change: ${summary['improvement']['cost_change_usd']:+,.2f})\n\n"
        "Be concise (3-5 sentences). Reference specific numbers when relevant. "
        "This is a carbon optimization assistant answering a user question."
    )

    # ── Session state ──────────────────────────────────────────────────
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # Clear button (top-right)
    _col_title, _col_clear = st.columns([6, 1])
    with _col_clear:
        if st.button("🗑️ Clear", disabled=not st.session_state.chat_history):
            st.session_state.chat_history = []
            st.rerun()

    # Drain any pending question injected by suggestion buttons
    _pending_q = st.session_state.pop("_pending_q", None)

    # ── Render conversation history ────────────────────────────────────
    for _msg in st.session_state.chat_history:
        with st.chat_message(_msg["role"]):
            st.markdown(_msg["content"])

    # ── Handle pending question (from suggestion buttons) ─────────────
    if _pending_q:
        with st.chat_message("user"):
            st.markdown(_pending_q)
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                _resp = LLMProvider("auto").chat(sys_prompt, _pending_q, temperature=0.7)
            st.markdown(_resp)
        st.session_state.chat_history.extend([
            {"role": "user", "content": _pending_q},
            {"role": "assistant", "content": _resp},
        ])

    # ── Handle live chat input ─────────────────────────────────────────
    if _user_input := st.chat_input("Ask about your carbon footprint, agents, or methodology…"):
        with st.chat_message("user"):
            st.markdown(_user_input)

        # Include recent history as context for follow-up questions
        _context = _user_input
        if st.session_state.chat_history:
            _recent = st.session_state.chat_history[-4:]  # last 4 messages (2 turns)
            _history_str = "\n".join(
                f"{m['role'].title()}: {m['content']}" for m in _recent
            )
            _context = f"Recent conversation:\n{_history_str}\n\nCurrent question: {_user_input}"

        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                _resp = LLMProvider("auto").chat(sys_prompt, _context, temperature=0.7)
            st.markdown(_resp)

        st.session_state.chat_history.extend([
            {"role": "user", "content": _user_input},
            {"role": "assistant", "content": _resp},
        ])

    # ── Suggestion buttons (shown only when conversation is empty) ─────
    if not st.session_state.chat_history and not _pending_q:
        st.markdown("#### 💡 Try asking:")
        _suggestions = [
            "What drove the most carbon savings?",
            "How does verification work?",
            "What was the cost impact of the optimization?",
            "How does the Governance agent decide what to approve?",
            "Explain the counterfactual MRV methodology.",
            "Which team performed best?",
        ]
        _s_cols = st.columns(2)
        for _i, _q in enumerate(_suggestions):
            if _s_cols[_i % 2].button(_q, key=f"_sq{_i}"):
                st.session_state["_pending_q"] = _q
                st.rerun()
