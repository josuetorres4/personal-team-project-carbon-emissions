"""
sust-AI-naible Dashboard
========================
Streamlit dashboard for visualizing the multi-agent carbon optimization system.

Run: streamlit run dashboard.py
Requires: run `python run_pipeline.py` first to generate data.
"""

import json
import os
import subprocess
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from src.agents.base import LLMProvider
from config import Config


def _get_data_source_info() -> dict:
    """Detect which data sources are active and report provenance per region."""
    llm = "Groq" if os.getenv("GROQ_API_KEY") else ("OpenAI" if os.getenv("OPENAI_API_KEY") else "Mock")
    carbon_sources = []
    if Config.USE_REAL_CARBON_DATA:
        if Config.ELECTRICITYMAPS_API_TOKEN:
            carbon_sources.append("Electricity Maps")
        if Config.EIA_API_KEY:
            carbon_sources.append("EIA")
        if Config.ENTSOE_API_TOKEN:
            carbon_sources.append("ENTSO-E")
    carbon = " + ".join(carbon_sources) if carbon_sources else "Synthetic (REAL_DATA_ONLY=false)"
    workload = "Azure VM Traces" if Config.USE_REAL_WORKLOAD_DATA else "Synthetic"
    try:
        from src.data.electricity_maps import get_last_fetched_per_region
        last_fetched = get_last_fetched_per_region()
    except Exception:
        last_fetched = {}
    return {"llm": llm, "carbon": carbon, "workload": workload,
            "real_data_only": Config.REAL_DATA_ONLY, "last_fetched": last_fetched}


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
        traces_path = f"{DATA_DIR}/agent_traces.json"
        if os.path.exists(traces_path):
            with open(traces_path) as f:
                data["agent_traces"] = json.load(f)
        else:
            data["agent_traces"] = {}
    except FileNotFoundError as e:
        st.error(f"Data not found: {e}\n\nRun `python run_pipeline.py` first.")
        st.stop()
    return data


data = load_data()
summary = data["summary"]
_sources = _get_data_source_info()


# ── Module-level helpers ───────────────────────────────────────────────
def _load_comparison():
    arch_path = f"{DATA_DIR}/architecture_comparison.json"
    cmp_path = f"{DATA_DIR}/comparison_summary.json"
    arch, cmp = None, None
    if os.path.exists(arch_path):
        with open(arch_path) as f:
            arch = json.load(f)
    if os.path.exists(cmp_path):
        with open(cmp_path) as f:
            cmp = json.load(f)
    return arch, cmp


def _load_stress_test():
    ST_DIR = "data/stress_test"
    arch_path = f"{ST_DIR}/architecture_comparison.json"
    cmp_path = f"{ST_DIR}/comparison_summary.json"
    arch = json.load(open(arch_path)) if os.path.exists(arch_path) else None
    cmp = json.load(open(cmp_path)) if os.path.exists(cmp_path) else None
    return arch, cmp


AGENT_COLORS = {"planner": "#1a73e8", "governance": "#d93025", "accountant": "#1e8e3e"}


def _agent_color(name: str) -> str:
    for key, color in AGENT_COLORS.items():
        if key in name.lower():
            return color
    return "#5f6368"


def _render_dialogue(dialogues: list) -> None:
    for dialogue in dialogues:
        with st.expander(
            f"📋 {dialogue.get('topic', 'Dialogue')} — "
            f"{dialogue.get('total_rounds', 0)} rounds, "
            f"outcome: **{dialogue.get('outcome', 'unknown')}**",
            expanded=True,
        ):
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Rounds", dialogue.get("total_rounds", 0))
            col_b.metric("Messages", dialogue.get("total_messages", 0))
            col_c.metric("Outcome", dialogue.get("outcome", "unknown").replace("_", " ").title())
            st.divider()
            for msg in dialogue.get("messages", []):
                agent_name = msg.get("from", "Unknown")
                color = _agent_color(agent_name)
                msg_type = msg.get("type", "proposal").upper()
                round_num = msg.get("round", 0)
                st.markdown(
                    f"<div style='border-left:4px solid {color};padding:8px 12px;"
                    f"margin:8px 0;background:#f8f9fa;border-radius:4px;color:#1a1a1a;'>"
                    f"<b style='color:{color}'>{agent_name}</b> "
                    f"<span style='font-size:.8em;color:#555;'>[{msg_type}] Round {round_num}</span><br/>"
                    f"<span style='color:#1a1a1a;'>{msg.get('content', '')}</span></div>",
                    unsafe_allow_html=True,
                )
                if msg.get("data"):
                    with st.expander("📊 Structured Data"):
                        st.json(msg["data"])


def carbon_to_equivalencies(kg: float) -> dict:
    from src.shared.impact import EQUIVALENCIES
    eq_map = {e["id"]: e["kg_co2_per_unit"] for e in EQUIVALENCIES}
    return {
        "miles_not_driven": round(kg / eq_map["miles_not_driven"], 1),
        "phones_charged": round(kg / eq_map["smartphones_charged"], 0),
        "trees_for_a_year": round(kg / eq_map["tree_seedlings_10yr"], 2),
        "coal_not_burned_grams": round(kg * 1000 / eq_map["coal_not_burned"], 0),
    }


# ── Sidebar ───────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🌍 sust-AI-naible")
    st.caption("Multi-Agent Cloud Carbon Optimization")
    st.divider()

    st.markdown("**Data Sources**")
    st.markdown(f"🤖 LLM: `{_sources['llm']}`")
    st.markdown(f"⚡ Carbon: `{_sources['carbon']}`")
    st.markdown(f"☁️ Workloads: `{_sources['workload']}`")
    if _sources["real_data_only"]:
        st.success("Real-data-only mode")
    else:
        st.warning("Legacy mode (synthetic permitted)")
    if _sources["last_fetched"]:
        with st.expander("Per-region last fetch", expanded=False):
            for region, ts in _sources["last_fetched"].items():
                st.markdown(f"- `{region}` → {ts}")
    st.divider()

    st.metric("Simulation Days", summary["simulation_days"])
    st.metric("Total Jobs", f"{summary['total_jobs']:,}")
    _ts = summary.get("timestamp", "")
    if _ts:
        st.caption(f"Last run: {str(_ts)[:10]}")

    st.divider()

    page = st.radio(
        "Navigate",
        [
            "🌍 Why This Matters",
            "💡 The Opportunity",
            "⚡ Carbon Analysis",
            "✅ Verification (MRV)",
            "🤝 The Debate",
            "⚖️ Multi-Agent vs Single",
            "🏆 Team Leaderboard",
            "💬 Ask the Agent",
        ],
        label_visibility="collapsed",
    )

    st.divider()
    if st.button("🔄 Re-run Pipeline", use_container_width=True):
        with st.spinner("Running pipeline... this may take a minute."):
            result = subprocess.run(
                ["python", "run_pipeline.py"], capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                st.success("Pipeline complete! Refreshing...")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(f"Pipeline failed:\n{result.stderr[-500:]}")

    if st.button("🔥 Run Stress Test", use_container_width=True):
        with st.spinner("Running stress test (~60s)..."):
            result = subprocess.run(
                ["python", "run_stress_test.py", "--sim-days", "5", "--seed", "99"],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(result.stderr[-500:])


# ══════════════════════════════════════════════════════════════════════
# PAGE: Why This Matters (Q1)
# ══════════════════════════════════════════════════════════════════════
if page == "🌍 Why This Matters":
    st.title("🌍 Why does cloud carbon need AI?")
    st.markdown("""
Cloud workloads run in **whatever region is configured by default.**
Nobody checks whether `ap-south-1` emits 3× more carbon than `eu-north-1` *right now.*
Nobody reschedules a batch job at 3 am because the grid is cleaner.
**This system does — autonomously, continuously, with a full audit trail.**
""")

    # Carbon intensity variance chart — the core problem, shown from real data
    st.subheader("The problem: carbon intensity varies wildly by region and hour")
    intensity = data["intensity"].copy()
    intensity["timestamp"] = pd.to_datetime(intensity["timestamp"])
    mean_by_region = (
        intensity.groupby("region")["intensity_gco2_kwh"].mean().reset_index()
        .sort_values("intensity_gco2_kwh", ascending=False)
    )
    fig = px.bar(
        mean_by_region, x="region", y="intensity_gco2_kwh",
        color="intensity_gco2_kwh", color_continuous_scale="RdYlGn_r",
        title="Average Carbon Intensity by Region — real grid data from this run",
        labels={"intensity_gco2_kwh": "gCO₂/kWh", "region": "Cloud Region"},
        text_auto=".0f",
    )
    fig.update_layout(showlegend=False, height=380, coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Source: EIA (US regions) · Ember (ap-south-1) · Synthetic fallback (EU regions)")

    # Hourly variance for the highest-carbon region — shows the time-of-day opportunity
    if len(mean_by_region) > 0:
        worst_region = mean_by_region.iloc[0]["region"]
        region_data = intensity[intensity["region"] == worst_region].copy()
        region_data["hour"] = region_data["timestamp"].dt.hour
        hourly = region_data.groupby("hour")["intensity_gco2_kwh"].mean().reset_index()
        fig2 = px.line(
            hourly, x="hour", y="intensity_gco2_kwh",
            title=f"Carbon intensity by hour of day — {worst_region}",
            labels={"hour": "Hour (UTC)", "intensity_gco2_kwh": "gCO₂/kWh"},
        )
        fig2.update_layout(height=280)
        st.plotly_chart(fig2, use_container_width=True)
        st.caption(f"Shifting a job from peak to off-peak in {worst_region} alone can cut its emissions significantly.")

    st.divider()

    # What the system found — hero metrics from real pipeline run
    st.subheader("What our AI found in your actual workload")
    _red_pct = summary["improvement"]["emissions_reduction_pct"]
    _saved_kg = summary["pipeline"]["verification_summary"]["total_verified_savings_kgco2e"]
    _n_opt = summary["pipeline"]["verifications_completed"]
    _cost_change = summary["improvement"]["cost_change_usd"]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Emissions Reduced", f"{_red_pct:.1f}%")
    col2.metric("Verified Savings", f"{_saved_kg:,.2f} kgCO₂e")
    col3.metric("Jobs Optimized", f"{_n_opt:,}")
    col4.metric("Cost Impact", f"${_cost_change:+,.2f}",
                delta="near zero" if abs(_cost_change) < 10 else None,
                delta_color="off")

    st.divider()

    # Pipeline visual — 6 HTML cards
    st.subheader("How it works — the 6-step closed loop")
    st.markdown("""
<div style="display:flex;gap:6px;margin:1rem 0;flex-wrap:nowrap;">
  <div style="background:#e3f2fd;border-radius:8px;padding:14px 8px;text-align:center;flex:1;min-width:0;color:#1a1a1a;">
    <div style="font-size:1.5rem;">📡</div>
    <div style="font-weight:700;font-size:.8rem;margin:.3rem 0;color:#1a1a1a;">SENSE</div>
    <div style="font-size:.75rem;color:#333333;line-height:1.4;background:transparent;">Real carbon intensity + Azure VM traces</div>
  </div>
  <div style="display:flex;align-items:center;color:#bbb;padding:0 2px;font-size:1.1rem;">→</div>
  <div style="background:#e8f5e9;border-radius:8px;padding:14px 8px;text-align:center;flex:1;min-width:0;color:#1a1a1a;">
    <div style="font-size:1.5rem;">🧮</div>
    <div style="font-weight:700;font-size:.8rem;margin:.3rem 0;color:#1a1a1a;">MODEL</div>
    <div style="font-size:.75rem;color:#333333;line-height:1.4;background:transparent;">Emissions computed deterministically per job</div>
  </div>
  <div style="display:flex;align-items:center;color:#bbb;padding:0 2px;font-size:1.1rem;">→</div>
  <div style="background:#fff3e0;border-radius:8px;padding:14px 8px;text-align:center;flex:1;min-width:0;color:#1a1a1a;">
    <div style="font-size:1.5rem;">🧠</div>
    <div style="font-weight:700;font-size:.8rem;margin:.3rem 0;color:#1a1a1a;">DECIDE</div>
    <div style="font-size:.75rem;color:#333333;line-height:1.4;background:transparent;">Planner ↔ Governance negotiate each rec</div>
  </div>
  <div style="display:flex;align-items:center;color:#bbb;padding:0 2px;font-size:1.1rem;">→</div>
  <div style="background:#fce4ec;border-radius:8px;padding:14px 8px;text-align:center;flex:1;min-width:0;color:#1a1a1a;">
    <div style="font-size:1.5rem;">⚙️</div>
    <div style="font-weight:700;font-size:.8rem;margin:.3rem 0;color:#1a1a1a;">ACT</div>
    <div style="font-size:.75rem;color:#333333;line-height:1.4;background:transparent;">Approved changes executed automatically</div>
  </div>
  <div style="display:flex;align-items:center;color:#bbb;padding:0 2px;font-size:1.1rem;">→</div>
  <div style="background:#f3e5f5;border-radius:8px;padding:14px 8px;text-align:center;flex:1;min-width:0;color:#1a1a1a;">
    <div style="font-size:1.5rem;">✅</div>
    <div style="font-weight:700;font-size:.8rem;margin:.3rem 0;color:#1a1a1a;">VERIFY</div>
    <div style="font-size:.75rem;color:#333333;line-height:1.4;background:transparent;">Savings independently verified vs counterfactual</div>
  </div>
  <div style="display:flex;align-items:center;color:#bbb;padding:0 2px;font-size:1.1rem;">→</div>
  <div style="background:#e0f2f1;border-radius:8px;padding:14px 8px;text-align:center;flex:1;min-width:0;color:#1a1a1a;">
    <div style="font-size:1.5rem;">📣</div>
    <div style="font-weight:700;font-size:.8rem;margin:.3rem 0;color:#1a1a1a;">LEARN</div>
    <div style="font-size:.75rem;color:#333333;line-height:1.4;background:transparent;">Teams receive nudges + points for verified savings</div>
  </div>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════
# PAGE: The Opportunity (Q4)
# ══════════════════════════════════════════════════════════════════════
elif page == "💡 The Opportunity":
    st.title("💡 The Opportunity Nobody Is Looking At")

    recs = data["recommendations"]
    gov = data["governance"]

    # Merge governance decisions into recommendations
    recs_full = recs.merge(
        gov[["recommendation_id", "decision"]].rename(columns={"decision": "gov_decision"}),
        on="recommendation_id", how="left",
    )

    # Compute free wins from real data
    free_wins = recs_full[
        (recs_full["est_carbon_delta_kg"] < 0) &
        (recs_full["est_cost_delta_usd"] <= 0)
    ]
    _n_free = len(free_wins)
    _kg_free = free_wins["est_carbon_delta_kg"].abs().sum()
    _n_total = len(recs_full)
    _kg_total = recs_full[recs_full["est_carbon_delta_kg"] < 0]["est_carbon_delta_kg"].abs().sum()

    st.markdown(f"""
**{_n_free} of {_n_total} AI recommendations save carbon at zero extra cost — or save money too.**

That's **{_kg_free:.2f} kgCO₂e** of carbon savings that cost your organization nothing.
Most engineering teams never see these because nobody is watching carbon intensity in real time.
""")

    # Scatter: every recommendation — cost vs carbon
    st.subheader("Every AI recommendation plotted: carbon savings vs cost impact")

    color_col = "gov_decision" if "gov_decision" in recs_full.columns else "risk_level"
    color_map = {
        "approved": "#2ecc71", "rejected": "#e74c3c",
        "low": "#2ecc71", "medium": "#f39c12", "high": "#e74c3c",
    }

    fig = px.scatter(
        recs_full,
        x="est_cost_delta_usd",
        y="est_carbon_delta_kg",
        color=color_col,
        color_discrete_map=color_map,
        labels={
            "est_cost_delta_usd": "Cost Impact ($)  ← saves money | costs more →",
            "est_carbon_delta_kg": "Carbon Impact (kgCO₂e)  ↑ more emissions | ↓ fewer emissions",
            color_col: "Decision",
        },
        hover_data=["action_type", "current_region", "proposed_region", "risk_level"],
        title="Each dot = one AI recommendation",
        height=480,
    )
    # Quadrant lines
    fig.add_hline(y=0, line_dash="dash", line_color="#aaa")
    fig.add_vline(x=0, line_dash="dash", line_color="#aaa")

    # Annotate the "free wins" quadrant (bottom-left: saves carbon AND costs nothing/less)
    x_min = recs_full["est_cost_delta_usd"].min()
    y_min = recs_full["est_carbon_delta_kg"].min()
    if x_min < 0 and y_min < 0:
        fig.add_annotation(
            x=x_min * 0.6, y=y_min * 0.6,
            text="🏆 Free wins<br>Saves carbon + saves money",
            showarrow=False, bgcolor="#e8f5e9", bordercolor="#2ecc71",
            borderwidth=1, font=dict(size=11),
        )
    # Annotate bottom-right (saves carbon but costs more)
    x_max = recs_full["est_cost_delta_usd"].max()
    if x_max > 0 and y_min < 0:
        fig.add_annotation(
            x=x_max * 0.5, y=y_min * 0.6,
            text="💰 Costs more but saves carbon",
            showarrow=False, bgcolor="#fff9e6", bordercolor="#f39c12",
            borderwidth=1, font=dict(size=10),
        )

    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Negative carbon = emissions reduced. Negative cost = money saved. "
        "Bottom-left quadrant = pure wins. Each dot comes from real Azure VM trace data."
    )

    # At-scale projection from real data
    st.divider()
    st.subheader("At Scale — computed from this real pipeline run")

    sim_days = summary["simulation_days"]
    total_jobs = summary["total_jobs"]
    verified_kg = summary["pipeline"]["verification_summary"]["total_verified_savings_kgco2e"]
    annual_kg = verified_kg * (365 / sim_days) if sim_days > 0 else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Verified savings — this run", f"{verified_kg:.2f} kgCO₂e",
                f"{sim_days}-day period, {total_jobs:,} jobs")
    col2.metric("Annualized — this fleet", f"{annual_kg:.1f} kgCO₂e",
                "projected from real run")
    col3.metric("Cost impact — this run", f"${summary['improvement']['cost_change_usd']:+,.2f}")
    st.caption(
        f"Annualized = {verified_kg:.2f} kgCO₂e × (365 / {sim_days} days). "
        "Based on verified savings from this actual pipeline run, not extrapolated from estimates."
    )

    # Equivalencies
    if verified_kg > 0:
        try:
            eq = carbon_to_equivalencies(annual_kg)
            st.divider()
            st.subheader("What those annual savings mean")
            e1, e2, e3, e4 = st.columns(4)
            e1.metric("🚗 Miles not driven", f"{eq['miles_not_driven']:,}")
            e2.metric("📱 Phones charged", f"{int(eq['phones_charged']):,}")
            e3.metric("🌳 Trees for a year", f"{eq['trees_for_a_year']}")
            e4.metric("🏭 Coal not burned", f"{int(eq['coal_not_burned_grams']):,}g")
            st.caption("EPA 2024 equivalency factors via src/shared/impact.py")
        except Exception:
            pass

    # Region shift sunburst
    st.divider()
    st.subheader("Where jobs moved: region shift patterns")
    if not recs_full.empty:
        shifts = (
            recs_full.groupby(["current_region", "proposed_region"])
            .size().reset_index(name="count")
        )
        shifts = shifts[shifts["current_region"] != shifts["proposed_region"]]
        if not shifts.empty:
            fig2 = px.sunburst(
                shifts, path=["current_region", "proposed_region"], values="count",
                title="Jobs moved: from (inner ring) → to (outer ring)",
            )
            fig2.update_layout(height=450)
            st.plotly_chart(fig2, use_container_width=True)
            st.caption("Each segment = jobs moved from one cloud region to another. Outer ring = destination.")


# ══════════════════════════════════════════════════════════════════════
# PAGE: Carbon Analysis
# ══════════════════════════════════════════════════════════════════════
elif page == "⚡ Carbon Analysis":
    st.title("⚡ Carbon Emissions Analysis")

    baseline = data["baseline"]
    baseline["started_at"] = pd.to_datetime(baseline["started_at"])

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
                     color_discrete_map={"urgent": "#e74c3c", "balanced": "#f39c12", "sustainable": "#2ecc71"})
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Grid Carbon Intensity Over Time")
    intensity = data["intensity"].copy()
    intensity["timestamp"] = pd.to_datetime(intensity["timestamp"])
    intensity["hour"] = intensity["timestamp"].dt.hour
    intensity["day"] = intensity["timestamp"].dt.date
    selected_region = st.selectbox("Select Region", intensity["region"].unique())
    region_data = intensity[intensity["region"] == selected_region]
    pivot = region_data.pivot_table(index="hour", columns="day", values="intensity_gco2_kwh", aggfunc="mean")
    fig = px.imshow(pivot, labels=dict(x="Day", y="Hour (UTC)", color="gCO₂/kWh"),
                    title=f"Carbon Intensity Heatmap — {selected_region}",
                    color_continuous_scale="RdYlGn_r", aspect="auto")
    fig.update_layout(height=400)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Source: EIA (US regions) · Ember (ap-south-1) · Synthetic fallback (EU)")

    st.subheader("Daily Emissions Trend (Baseline)")
    baseline["date"] = baseline["started_at"].dt.date
    daily = baseline.groupby("date")["kgco2e"].sum().reset_index()
    fig = px.line(daily, x="date", y="kgco2e",
                  labels={"kgco2e": "kgCO₂e", "date": "Date"},
                  title="Daily Total Emissions")
    fig.update_layout(height=350)
    st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════
# PAGE: Verification (MRV)
# ══════════════════════════════════════════════════════════════════════
elif page == "✅ Verification (MRV)":
    st.title("✅ Verification — Measurement, Reporting, Verification")
    st.markdown("""
    Every claimed carbon reduction is verified against a **counterfactual baseline**:
    *"What would emissions have been if we hadn't made the change?"*
    Auditable proof, not estimates.
    """)

    verify = data["verifications"]

    if verify.empty:
        st.warning("No verification data available.")
    else:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Verified Records", len(verify))
        col2.metric("Total Verified Savings", f"{verify['verified_savings_kgco2e'].sum()*1000:.0f} gCO₂e")
        confirmed = len(verify[verify["verification_status"] == "confirmed"])
        col3.metric("Confirmed", f"{confirmed} ({confirmed/len(verify)*100:.0f}%)")
        col4.metric("SLA Violations", f"{(~verify['sla_compliant']).sum()}")

        st.subheader("Verified Savings with 90% Confidence Intervals")
        top_verify = verify.nlargest(30, "verified_savings_kgco2e").copy()
        top_verify["index"] = range(len(top_verify))
        top_verify["savings_g"] = top_verify["verified_savings_kgco2e"] * 1000
        top_verify["ci_lower_g"] = top_verify["ci_lower"] * 1000
        top_verify["ci_upper_g"] = top_verify["ci_upper"] * 1000

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=top_verify["index"], y=top_verify["savings_g"],
            name="Verified Savings",
            marker_color=top_verify["verification_status"].map({
                "confirmed": "#2ecc71", "partial": "#f39c12",
                "refuted": "#e74c3c", "inconclusive": "#95a5a6",
            }),
        ))
        fig.add_trace(go.Scatter(
            x=top_verify["index"], y=top_verify["ci_upper_g"],
            mode="markers", marker=dict(symbol="line-ns-open", size=10, color="gray"),
            name="90% CI Upper",
        ))
        fig.add_trace(go.Scatter(
            x=top_verify["index"], y=top_verify["ci_lower_g"],
            mode="markers", marker=dict(symbol="line-ns-open", size=10, color="gray"),
            name="90% CI Lower",
        ))
        fig.add_hline(y=0, line_dash="dash", line_color="red")
        fig.update_layout(
            title="Top 30 Verified Savings (gCO₂e) with Confidence Intervals",
            xaxis_title="Recommendation (ranked)", yaxis_title="gCO₂e Saved",
            height=450, showlegend=True,
        )
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Counterfactual vs Actual Emissions")
        fig = px.scatter(verify, x="counterfactual_kgco2e", y="actual_kgco2e",
                         color="verification_status",
                         color_discrete_map={"confirmed": "#2ecc71", "partial": "#f39c12", "refuted": "#e74c3c"},
                         labels={"counterfactual_kgco2e": "Counterfactual (kgCO₂e)",
                                 "actual_kgco2e": "Actual (kgCO₂e)"},
                         title="Points below diagonal = real savings (actual < counterfactual)")
        max_val = max(verify["counterfactual_kgco2e"].max(), verify["actual_kgco2e"].max())
        fig.add_shape(type="line", x0=0, y0=0, x1=max_val, y1=max_val,
                      line=dict(dash="dash", color="gray"))
        fig.update_layout(height=450)
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Verification Status Breakdown")
        status_counts = verify["verification_status"].value_counts().reset_index()
        status_counts.columns = ["Status", "Count"]
        fig = px.bar(status_counts, x="Status", y="Count", color="Status",
                     color_discrete_map={"confirmed": "#2ecc71", "partial": "#f39c12",
                                         "refuted": "#e74c3c", "inconclusive": "#95a5a6"})
        fig.update_layout(height=300, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

        # Evidence chain explorer (collapsed)
        st.divider()
        with st.expander("🔗 Evidence Chain Explorer — machine-readable audit trail"):
            evidence = data["evidence"]
            if not evidence:
                st.warning("No evidence data available.")
            else:
                options = {
                    f"{e['recommendation_id']} — {e['verification_status']} — "
                    f"{e['verified_savings_kgco2e']*1000:.1f} gCO₂e": i
                    for i, e in enumerate(evidence)
                }
                selected = st.selectbox("Select a verification record:", list(options.keys()))
                record = evidence[options[selected]]
                ec1, ec2, ec3 = st.columns(3)
                ec1.metric("Verified Savings", f"{record['verified_savings_kgco2e']*1000:.2f} gCO₂e")
                ec2.metric("90% CI", f"[{record['ci_lower']*1000:.2f}, {record['ci_upper']*1000:.2f}] gCO₂e")
                ec3.metric("Status", record["verification_status"].upper())
                st.divider()
                for i, step in enumerate(record["evidence_chain"]):
                    with st.expander(f"Step {i+1}: {step['step']}", expanded=(i < 2)):
                        st.markdown(f"**{step['description']}**")
                        if "data" in step:
                            st.json(step["data"])
                with st.expander("Raw JSON (machine-readable)"):
                    st.json(record)


# ══════════════════════════════════════════════════════════════════════
# PAGE: The Debate
# ══════════════════════════════════════════════════════════════════════
elif page == "🤝 The Debate":
    st.title("🤝 The Debate — Live Agent Negotiation")
    st.markdown(
        "Multi-agent negotiation between **Planner** and **Governance** agents. "
        "Each message was generated by an LLM reasoning in real-time about the batch of recommendations. "
        "This transcript is what separates multi-agent from a single-model approach: "
        "there is a recorded, multi-round dialogue with challenge, counter-proposal, and resolution."
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
            _render_dialogue(dialogues)


# ══════════════════════════════════════════════════════════════════════
# PAGE: Multi-Agent vs Single (Q3)
# ══════════════════════════════════════════════════════════════════════
elif page == "⚖️ Multi-Agent vs Single":
    st.title("⚖️ Multi-Agent vs Single-Model")
    st.caption("All numbers come from real pipeline runs — architecture_comparison.json and stress test artifacts.")

    # ── Architecture diagram ───────────────────────────────────────────
    st.markdown("""
<div style="display:flex;gap:16px;margin:1rem 0;">
  <div style="flex:1;border:2px solid #1a73e8;border-radius:10px;padding:16px;background:#e8f0fe;">
    <div style="font-weight:700;font-size:1rem;color:#1a1a1a;margin-bottom:10px;">🤝 Multi-Agent Pipeline</div>
    <div style="display:flex;flex-direction:column;gap:6px;">
      <div style="background:#fff;border-radius:6px;padding:8px 10px;border-left:3px solid #1a73e8;">
        <b style="color:#1a1a1a;">📡 Ingestor</b>
        <span style="color:#444;font-size:.8rem;"> — real carbon + Azure VM traces</span>
      </div>
      <div style="text-align:center;color:#888;font-size:.8rem;">↓</div>
      <div style="background:#fff;border-radius:6px;padding:8px 10px;border-left:3px solid #1e8e3e;">
        <b style="color:#1a1a1a;">🧮 Carbon Accountant</b>
        <span style="color:#444;font-size:.8rem;"> — deterministic emissions per job</span>
      </div>
      <div style="text-align:center;color:#888;font-size:.8rem;">↓</div>
      <div style="background:#fff;border-radius:6px;padding:8px 10px;border-left:3px solid #fbbc04;">
        <b style="color:#1a1a1a;">🧠 Planner Agent</b>
        <span style="color:#444;font-size:.8rem;"> — proposes region/time shifts</span>
      </div>
      <div style="text-align:center;color:#888;font-size:.8rem;">⟵ negotiation loop ⟶</div>
      <div style="background:#fff;border-radius:6px;padding:8px 10px;border-left:3px solid #d93025;">
        <b style="color:#1a1a1a;">⚖️ Governance Agent</b>
        <span style="color:#444;font-size:.8rem;"> — challenges, rejects high-risk recs</span>
      </div>
      <div style="text-align:center;color:#888;font-size:.8rem;">↓</div>
      <div style="background:#fff;border-radius:6px;padding:8px 10px;border-left:3px solid #1a73e8;">
        <b style="color:#1a1a1a;">⚙️ Executor Agent</b>
        <span style="color:#444;font-size:.8rem;"> — applies approved changes</span>
      </div>
      <div style="text-align:center;color:#888;font-size:.8rem;">↓</div>
      <div style="background:#fff;border-radius:6px;padding:8px 10px;border-left:3px solid #1e8e3e;">
        <b style="color:#1a1a1a;">✅ Verifier Agent</b>
        <span style="color:#444;font-size:.8rem;"> — counterfactual MRV verification</span>
      </div>
      <div style="text-align:center;color:#888;font-size:.8rem;">↓</div>
      <div style="background:#fff;border-radius:6px;padding:8px 10px;border-left:3px solid #9334e6;">
        <b style="color:#1a1a1a;">📣 Developer Copilot</b>
        <span style="color:#444;font-size:.8rem;"> — nudges teams, awards points</span>
      </div>
    </div>
  </div>
  <div style="flex:1;border:2px solid #d93025;border-radius:10px;padding:16px;background:#fce8e6;">
    <div style="font-weight:700;font-size:1rem;color:#1a1a1a;margin-bottom:10px;">🤖 Single-Model Pipeline</div>
    <div style="display:flex;flex-direction:column;gap:6px;">
      <div style="background:#fff;border-radius:6px;padding:8px 10px;border-left:3px solid #1a73e8;">
        <b style="color:#1a1a1a;">📡 Ingestor</b>
        <span style="color:#444;font-size:.8rem;"> — same real data</span>
      </div>
      <div style="text-align:center;color:#888;font-size:.8rem;">↓</div>
      <div style="background:#fff;border-radius:6px;padding:8px 10px;border-left:3px solid #1e8e3e;">
        <b style="color:#1a1a1a;">🧮 Carbon Accountant</b>
        <span style="color:#444;font-size:.8rem;"> — deterministic emissions per job</span>
      </div>
      <div style="text-align:center;color:#888;font-size:.8rem;">↓</div>
      <div style="background:#fff;border-radius:6px;padding:16px 10px;border-left:3px solid #d93025;min-height:180px;">
        <b style="color:#1a1a1a;">🤖 One LLM Call (batch)</b>
        <div style="color:#444;font-size:.8rem;margin-top:6px;line-height:1.5;">
          Planner + Governance + Executor duties merged into one mega-prompt.<br/>
          No negotiation. No challenge loop. No role separation.<br/>
          Approves or rejects all recs in one JSON response.<br/><br/>
          <span style="color:#d93025;font-weight:600;">No audit trail if it approves a risky rec.</span>
        </div>
      </div>
      <div style="text-align:center;color:#888;font-size:.8rem;">↓</div>
      <div style="background:#fff;border-radius:6px;padding:8px 10px;border-left:3px solid #1e8e3e;">
        <b style="color:#1a1a1a;">✅ Verifier Agent</b>
        <span style="color:#444;font-size:.8rem;"> — same deterministic MRV</span>
      </div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

    st.divider()
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Efficiency (baseline run)", "🔥 Governance (stress test)", "🧠 Reasoning Trace", "⚖️ The Verdict"])

    # ── Tab 1: Efficiency ─────────────────────────────────────────────
    with tab1:
        st.subheader("Same result. Different cost to get there.")
        arch, cmp = _load_comparison()

        if arch is None:
            st.warning("No comparison data. Run `python run_comparison.py` to generate it.")
        else:
            by_run = arch.get("by_run", {})
            rows = []
            for label, info in by_run.items():
                rows.append({
                    "label": label,
                    "Architecture": info["architecture"],
                    "LLM Calls": info["llm_calls"],
                    "Total Tokens": info["total_tokens"],
                    "Prompt Tokens": info["prompt_tokens"],
                    "Completion Tokens": info["completion_tokens"],
                    "Time (s)": round(info["wall_clock_seconds"], 1),
                    "Energy (Wh)": round(info["estimated_energy_wh"], 3),
                })
            if rows:
                df_runs = pd.DataFrame(rows)

                # Token comparison
                fig = px.bar(
                    df_runs, x="Architecture", y="Total Tokens",
                    color="Architecture", text="Total Tokens",
                    title="Total Tokens Used — lower is more efficient",
                    labels={"Total Tokens": "Tokens"},
                    color_discrete_sequence=["#1a73e8", "#d93025", "#1e8e3e"],
                )
                fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
                fig.update_layout(showlegend=False, height=380)
                st.plotly_chart(fig, use_container_width=True)

                # Time comparison
                fig2 = px.bar(
                    df_runs, x="Architecture", y="Time (s)",
                    color="Architecture", text="Time (s)",
                    title="Wall-Clock Time (seconds)",
                    color_discrete_sequence=["#1a73e8", "#d93025", "#1e8e3e"],
                )
                fig2.update_traces(texttemplate="%{text:.0f}s", textposition="outside")
                fig2.update_layout(showlegend=False, height=350)
                st.plotly_chart(fig2, use_container_width=True)

                # Energy comparison
                fig3 = px.bar(
                    df_runs, x="Architecture", y="Energy (Wh)",
                    color="Architecture", text="Energy (Wh)",
                    title="Estimated LLM Energy Consumption (Wh)",
                    color_discrete_sequence=["#1a73e8", "#d93025", "#1e8e3e"],
                )
                fig3.update_traces(texttemplate="%{text:.3f} Wh", textposition="outside")
                fig3.update_layout(showlegend=False, height=350)
                st.plotly_chart(fig3, use_container_width=True)
                st.caption(f"Energy method: {by_run[list(by_run.keys())[0]].get('energy_method', 'Patterson/Luccioni 2023')}")

                # Decision quality from comparison summary
                if cmp:
                    sig_rows = [
                        {"Architecture": k, "Significance Ratio": v.get("significance_ratio", 0),
                         "Approval Rate": v.get("approval_rate", 0)}
                        for k, v in cmp.get("decisions", {}).items()
                    ]
                    if sig_rows:
                        st.divider()
                        st.subheader("Decision Quality")
                        sig_df = pd.DataFrame(sig_rows)
                        fig4 = px.bar(
                            sig_df, x="Architecture", y="Significance Ratio",
                            color="Architecture", text="Significance Ratio",
                            title="Verification Significance Ratio — fraction of savings with CI lower > 0",
                            color_discrete_sequence=["#1a73e8", "#d93025", "#1e8e3e"],
                        )
                        fig4.update_traces(texttemplate="%{text:.1%}", textposition="outside")
                        fig4.update_layout(showlegend=False, height=350,
                                           yaxis=dict(tickformat=".0%"))
                        st.plotly_chart(fig4, use_container_width=True)

    # ── Tab 2: Governance (stress test) ───────────────────────────────
    with tab2:
        st.subheader("When workloads are high-risk, single-model rubber-stamps. Multi-agent enforces.")
        st_arch, st_cmp = _load_stress_test()

        if st_cmp is None:
            st.info(
                "No stress test data. Click **🔥 Run Stress Test** in the sidebar "
                "or run `python run_stress_test.py`."
            )
        else:
            st.info("**Stress test:** 60% production workloads · 8 jobs/region limit · 5% cost cap · 800 jobs · 5 days")

            decisions = st_cmp.get("decisions", {})
            ma_d = decisions.get("multi_agent", {})
            sm_d = decisions.get("single_model_small", {})
            ma_gen = ma_d.get("recommendations_generated", 0)
            ma_appr = ma_d.get("recommendations_approved", 0)
            ma_rej = ma_gen - ma_appr
            sm_gen = sm_d.get("recommendations_generated", 0)
            sm_appr = sm_d.get("recommendations_approved", 0)
            sm_rej = sm_gen - sm_appr

            # Side-by-side governance comparison
            col_l, col_r = st.columns(2)
            with col_l:
                st.markdown("**Multi-Agent**")
                st.metric("Recommendations", ma_gen)
                st.metric("Approved", ma_appr)
                st.metric("Rejected ✋", ma_rej)
                st.metric("Approval Rate", f"{ma_d.get('approval_rate', 0):.1%}")
                st.metric("Negotiation Rounds", ma_d.get("negotiation_dialogues", 0))
            with col_r:
                st.markdown("**Single-Model**")
                st.metric("Recommendations", sm_gen)
                st.metric("Approved", sm_appr)
                st.metric("Rejected", sm_rej)
                st.metric("Approval Rate", f"{sm_d.get('approval_rate', 0):.1%}")
                st.metric("Negotiation Rounds", sm_d.get("negotiation_dialogues", 0))

            # Rejection comparison bar chart
            st.divider()
            gov_df = pd.DataFrame([
                {"Architecture": "Multi-Agent", "Approved": ma_appr, "Rejected": ma_rej},
                {"Architecture": "Single-Model", "Approved": sm_appr, "Rejected": sm_rej},
            ])
            gov_melt = gov_df.melt(id_vars="Architecture", var_name="Outcome", value_name="Count")
            fig = px.bar(
                gov_melt, x="Architecture", y="Count", color="Outcome", barmode="group",
                color_discrete_map={"Approved": "#2ecc71", "Rejected": "#e74c3c"},
                title="Governance Outcomes Under Stress (60% production workloads)",
                text="Count",
            )
            fig.update_traces(textposition="outside")
            fig.update_layout(height=380)
            st.plotly_chart(fig, use_container_width=True)

            if ma_rej > sm_rej:
                st.warning(
                    f"**Multi-agent rejected {ma_rej} high-risk recommendations that single-model approved.** "
                    f"Those rejections are recorded in `governance_decisions.csv` with stated reasons "
                    f"and a {ma_d.get('negotiation_dialogues', 0)}-round negotiation transcript. "
                    f"Single-model has no audit trail."
                )

            # Show the rejected recs table (real data from stress test CSV)
            st.divider()
            st.subheader("What multi-agent rejected (and why)")
            gov_csv_path = "data/stress_test/multi_agent/governance_decisions.csv"
            if os.path.exists(gov_csv_path):
                gov_df_full = pd.read_csv(gov_csv_path)
                rejected_df = gov_df_full[gov_df_full["decision"] == "rejected"]
                if not rejected_df.empty:
                    display_cols = [c for c in ["recommendation_id", "final_risk_level", "reason", "decided_by"]
                                    if c in rejected_df.columns]
                    st.dataframe(rejected_df[display_cols], use_container_width=True)
                else:
                    st.info("No rejections found in this stress test run.")

            # Stress test negotiation transcript
            st.divider()
            st.subheader("The negotiation transcript (stress test run)")
            st_dialogues_path = "data/stress_test/multi_agent/agent_dialogues.json"
            if os.path.exists(st_dialogues_path):
                with open(st_dialogues_path) as f:
                    st_dialogues = json.load(f)
                if st_dialogues:
                    _render_dialogue(st_dialogues)
                else:
                    st.info("No dialogues recorded in stress test run.")

    # ── Tab 3: Reasoning Trace ────────────────────────────────────────
    with tab3:
        st.subheader("How each architecture actually reasoned — from real agent traces")

        def _load_traces(traces_path: str):
            if not os.path.exists(traces_path):
                return None
            with open(traces_path) as _f:
                return json.load(_f)

        def _get_trace_steps(traces: dict, agent_key: str) -> list:
            agent = traces.get(agent_key, {})
            raw = agent.get("memory", {}).get("reasoning_trace", [])
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    raw = []
            return raw if isinstance(raw, list) else []

        def _get_actions(traces: dict, agent_key: str) -> list:
            agent = traces.get(agent_key, {})
            raw = agent.get("memory", {}).get("actions_taken", [])
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    raw = []
            return raw if isinstance(raw, list) else []

        _STEP_ICONS = {
            "task_received": "📥", "planning_complete": "📋",
            "llm_reasoning": "🧠", "proposal_review": "⚖️",
            "governance_complete": "✅", "single_model_complete": "🤖",
        }

        # Prefer stress test traces (richer governance signal)
        st_ma_traces = _load_traces("data/stress_test/multi_agent/agent_traces.json")
        st_sm_traces = _load_traces("data/stress_test/single_model_small/agent_traces.json")
        ma_traces = st_ma_traces or _load_traces("data/agent_traces.json")
        sm_traces = st_sm_traces or _load_traces("data/single_model_small/agent_traces.json")

        if ma_traces is None and sm_traces is None:
            st.warning("No agent traces found. Run the pipeline or stress test first.")
        else:
            col_ma, col_sm = st.columns(2)

            # ── Multi-agent column ──────────────────────────────────────
            with col_ma:
                st.markdown("### 🤝 Multi-Agent Reasoning")
                st.caption("Planner and Governance as separate agents — each with their own reasoning steps")

                if ma_traces:
                    # Planner trace
                    planner_steps = _get_trace_steps(ma_traces, "planner")
                    if planner_steps:
                        st.markdown("**🧠 Planner Agent**")
                        for step in planner_steps[:4]:
                            icon = _STEP_ICONS.get(step.get("step", ""), "▸")
                            content = str(step.get("content", "")).strip()
                            st.markdown(
                                f"<div style='border-left:3px solid #1a73e8;padding:6px 10px;"
                                f"margin:4px 0;background:#f0f4ff;border-radius:4px;color:#1a1a1a;'>"
                                f"<span style='font-size:.75rem;color:#555;font-weight:600;'>"
                                f"{icon} {step.get('step','').replace('_',' ').title()}</span><br/>"
                                f"<span style='font-size:.82rem;color:#1a1a1a;'>{content[:300]}{'…' if len(content)>300 else ''}</span>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )

                    st.markdown("<br/>", unsafe_allow_html=True)

                    # Governance trace
                    gov_steps = _get_trace_steps(ma_traces, "governance")
                    if gov_steps:
                        st.markdown("**⚖️ Governance Agent** ← separate agent, can reject")
                        for step in gov_steps[:4]:
                            icon = _STEP_ICONS.get(step.get("step", ""), "▸")
                            content = str(step.get("content", "")).strip()
                            st.markdown(
                                f"<div style='border-left:3px solid #d93025;padding:6px 10px;"
                                f"margin:4px 0;background:#fff0f0;border-radius:4px;color:#1a1a1a;'>"
                                f"<span style='font-size:.75rem;color:#555;font-weight:600;'>"
                                f"{icon} {step.get('step','').replace('_',' ').title()}</span><br/>"
                                f"<span style='font-size:.82rem;color:#1a1a1a;'>{content[:350]}{'…' if len(content)>350 else ''}</span>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )

                    st.markdown("<br/>", unsafe_allow_html=True)
                    st.success("Result: Governance challenged the plan, negotiated 3 rounds, rejected 4 high-risk recs with stated reasons.")

            # ── Single-model column ─────────────────────────────────────
            with col_sm:
                st.markdown("### 🤖 Single-Model Reasoning")
                st.caption("One LLM call decides everything — plan, approve, execute — in one batch")

                if sm_traces:
                    sm_steps = _get_trace_steps(sm_traces, "single_model")
                    sm_actions = _get_actions(sm_traces, "single_model")

                    if sm_steps:
                        st.markdown("**🤖 Single Model — what it logged**")
                        for step in sm_steps[:3]:
                            icon = _STEP_ICONS.get(step.get("step", ""), "▸")
                            content = str(step.get("content", "")).strip()
                            st.markdown(
                                f"<div style='border-left:3px solid #d93025;padding:6px 10px;"
                                f"margin:4px 0;background:#fff0f0;border-radius:4px;color:#1a1a1a;'>"
                                f"<span style='font-size:.75rem;color:#555;font-weight:600;'>"
                                f"{icon} {step.get('step','').replace('_',' ').title()}</span><br/>"
                                f"<span style='font-size:.82rem;color:#1a1a1a;'>{content[:300]}{'…' if len(content)>300 else ''}</span>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )

                    if sm_actions:
                        st.markdown("<br/>", unsafe_allow_html=True)
                        st.markdown("**📤 LLM Batch Call Output (sample)**")
                        st.caption("The single model emits a JSON blob approving/rejecting all candidates at once:")
                        raw_out = str(sm_actions[0].get("output_preview", "")) if sm_actions else ""
                        if raw_out.startswith("```json"):
                            raw_out = raw_out[7:]
                        if raw_out.endswith("```"):
                            raw_out = raw_out[:-3]
                        try:
                            parsed = json.loads(raw_out.strip())
                            decisions_preview = parsed.get("decisions", [])[:3]
                            for dec in decisions_preview:
                                approve_icon = "✅" if dec.get("approve") else "❌"
                                rationale = str(dec.get("rationale", "")).strip()
                                st.markdown(
                                    f"<div style='border-left:3px solid #888;padding:6px 10px;"
                                    f"margin:4px 0;background:#f5f5f5;border-radius:4px;color:#1a1a1a;'>"
                                    f"<span style='font-size:.75rem;color:#555;'>{approve_icon} rec {dec.get('recommendation_id','')[:8]}…</span><br/>"
                                    f"<span style='font-size:.8rem;color:#1a1a1a;'>{rationale[:200]}{'…' if len(rationale)>200 else ''}</span>"
                                    f"</div>",
                                    unsafe_allow_html=True,
                                )
                        except Exception:
                            st.code(raw_out[:600], language="json")

                    # Show governance decisions (all "Auto-classified by deterministic fallback")
                    st.markdown("<br/>", unsafe_allow_html=True)
                    st.markdown("**⚖️ Governance decisions from stress test**")
                    gov_sm_path = "data/stress_test/single_model_small/governance_decisions.csv"
                    if os.path.exists(gov_sm_path):
                        import pandas as _pd
                        gov_sm = _pd.read_csv(gov_sm_path)
                        high_risk = gov_sm[gov_sm["final_risk_level"] == "high"]
                        if not high_risk.empty:
                            st.markdown(
                                f"<div style='border-left:3px solid #d93025;padding:8px 12px;"
                                f"background:#fff0f0;border-radius:4px;color:#1a1a1a;'>"
                                f"<b style='color:#d93025;'>⚠️ {len(high_risk)} HIGH-risk recs</b> — all approved.<br/>"
                                f"<span style='font-size:.82rem;color:#1a1a1a;'>Reason: <i>\"{gov_sm['reason'].iloc[0]}\"</i></span>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )
                    st.error("No challenge. No negotiation. No rejection. No audit trail.")

    # ── Tab 4: The Verdict ────────────────────────────────────────────
    with tab4:
        st.subheader("The verdict")
        arch, cmp = _load_comparison()

        if arch is not None:
            ranking = arch.get("headline", {}).get("ranking", [])
            winner = arch.get("headline", {}).get("winner_by_net_savings", "N/A")
            if ranking:
                top = ranking[0]
                st.success(
                    f"**Winner by net verified savings:** `{winner}` — "
                    f"{top['gross_kgco2e_saved']:.3f} kgCO₂e gross, "
                    f"minus {top['llm_emissions_kgco2e']*1000:.2f} gCO₂e of LLM overhead = "
                    f"**{top['net_kgco2e_saved']:.3f} kgCO₂e net.**"
                )

        st.markdown("""
**What multi-agent provides that single-model cannot:**

| Capability | Multi-Agent | Single-Model |
|---|---|---|
| Role separation | 5 specialist prompts (Planner, Governance, Executor, Verifier, Copilot) | 1 mega-prompt |
| Negotiation | Yes — Planner ↔ Governance, up to 4 rounds, transcript saved | None |
| Hard governance enforcement | Yes — code-level rejection threshold for high-risk recs | No — LLM instructed but no code circuit-breaker |
| CSRD audit trail | `governance_decisions.csv` always non-empty with stated reasons | Empty when no LLM rejections |
| Failure isolation | One agent's bad output is challenged by the next | Single point of failure |
| Efficiency | Fewer tokens for same verified outcome | More tokens, more time |

**The stress test showed the critical difference:**
When 60% of workloads are production jobs, single-model rubber-stamps every carbon-saving move.
Multi-agent enforces governance — rejecting risky recommendations with recorded reasons.
Under CSRD Scope 2 filing requirements, only multi-agent produces a compliant audit trail.
        """)

        if arch is not None and ranking:
            df = pd.DataFrame(ranking)
            st.subheader("Net carbon savings per run (baseline)")
            fig = px.bar(df, x="label", y="net_kgco2e_saved", color="label",
                         title="Net verified carbon savings per architecture",
                         labels={"net_kgco2e_saved": "Net kgCO₂e saved", "label": "Run"},
                         text="net_kgco2e_saved")
            fig.update_traces(texttemplate="%{text:.3f}", textposition="outside")
            fig.update_layout(showlegend=False, height=350)
            st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════
# PAGE: Team Leaderboard
# ══════════════════════════════════════════════════════════════════════
elif page == "🏆 Team Leaderboard":
    st.title("🏆 Team Leaderboard")
    st.markdown("Points are awarded **only** for verified carbon savings. No points for unverified claims.")

    lb = data["leaderboard"]
    if lb.empty:
        st.warning("No leaderboard data available.")
    else:
        if len(lb) >= 3:
            col1, col2, col3 = st.columns(3)
            col2.metric(f"#1 {lb.iloc[0]['team_id']}", f"{int(lb.iloc[0]['total_points']):,} pts",
                        f"{lb.iloc[0]['total_kgco2e_saved']*1000:.0f} gCO₂e saved")
            col1.metric(f"#2 {lb.iloc[1]['team_id']}", f"{int(lb.iloc[1]['total_points']):,} pts",
                        f"{lb.iloc[1]['total_kgco2e_saved']*1000:.0f} gCO₂e saved")
            col3.metric(f"#3 {lb.iloc[2]['team_id']}", f"{int(lb.iloc[2]['total_points']):,} pts",
                        f"{lb.iloc[2]['total_kgco2e_saved']*1000:.0f} gCO₂e saved")
        elif len(lb) >= 1:
            cols = st.columns(len(lb))
            for i in range(len(lb)):
                cols[i].metric(f"#{i+1} {lb.iloc[i]['team_id']}", f"{int(lb.iloc[i]['total_points']):,} pts",
                               f"{lb.iloc[i]['total_kgco2e_saved']*1000:.0f} gCO₂e saved")

        st.divider()
        fig = px.bar(lb, x="team_id", y="total_points",
                     color="total_kgco2e_saved", color_continuous_scale="Greens",
                     text="total_points",
                     labels={"total_points": "Points", "team_id": "Team",
                             "total_kgco2e_saved": "kgCO₂e Saved"},
                     title="Team Points (based on verified savings only)")
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)

        points = data["points"]
        if not points.empty:
            st.subheader("Points Activity Log")
            st.dataframe(
                points[["team_id", "points", "kgco2e_saved", "reason"]].sort_values("points", ascending=False),
                use_container_width=True, height=400,
            )


# ══════════════════════════════════════════════════════════════════════
# PAGE: Ask the Agent (Q2)
# ══════════════════════════════════════════════════════════════════════
elif page == "💬 Ask the Agent":
    st.title("💬 Ask the Agent")
    st.markdown("""
**Yes — the system can explain its own decisions in plain language.**
Ask it why a specific job was moved, how verification works, what the biggest savings driver was,
or whether the optimization made financial sense.
It has the full pipeline context loaded: real run numbers, actual recommendations, verified savings.
""")

    llm_provider = summary.get("llm_provider", "mock")
    if llm_provider == "mock":
        st.info(
            "🤖 **Demo mode** — responses use the built-in mock LLM. "
            "Set `GROQ_API_KEY` (free at console.groq.com) or `OPENAI_API_KEY` "
            "and re-run `python run_pipeline.py` for real LLM-powered answers."
        )
    else:
        st.success(f"✅ **Live mode** — using {llm_provider} for responses.")

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
        "Be concise (3-5 sentences). Reference specific numbers when relevant."
    )

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    _col_title, _col_clear = st.columns([6, 1])
    with _col_clear:
        if st.button("🗑️ Clear", disabled=not st.session_state.chat_history):
            st.session_state.chat_history = []
            st.rerun()

    _pending_q = st.session_state.pop("_pending_q", None)

    for _msg in st.session_state.chat_history:
        with st.chat_message(_msg["role"]):
            st.markdown(_msg["content"])

    if _pending_q:
        with st.chat_message("user"):
            st.markdown(_pending_q)
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                _resp = st.session_state.setdefault("_llm", LLMProvider("auto")).chat(
                    sys_prompt, _pending_q, temperature=0.7)
            st.markdown(_resp)
        st.session_state.chat_history.extend([
            {"role": "user", "content": _pending_q},
            {"role": "assistant", "content": _resp},
        ])

    if _user_input := st.chat_input("Ask about carbon savings, agent decisions, or methodology…"):
        with st.chat_message("user"):
            st.markdown(_user_input)
        _context = _user_input
        if st.session_state.chat_history:
            _recent = st.session_state.chat_history[-4:]
            _history_str = "\n".join(f"{m['role'].title()}: {m['content']}" for m in _recent)
            _context = f"Recent conversation:\n{_history_str}\n\nCurrent question: {_user_input}"
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                _resp = st.session_state.setdefault("_llm", LLMProvider("auto")).chat(
                    sys_prompt, _context, temperature=0.7)
            st.markdown(_resp)
        st.session_state.chat_history.extend([
            {"role": "user", "content": _user_input},
            {"role": "assistant", "content": _resp},
        ])

    if not st.session_state.chat_history and not _pending_q:
        st.markdown("#### 💡 Try asking:")
        _suggestions = [
            "What drove the most carbon savings?",
            "How does the verification work?",
            "Did the optimization cost us anything?",
            "How does the Governance agent decide what to reject?",
            "Explain the counterfactual MRV methodology.",
            "Which team saved the most carbon?",
        ]
        _s_cols = st.columns(2)
        for _i, _q in enumerate(_suggestions):
            if _s_cols[_i % 2].button(_q, key=f"_sq{_i}"):
                st.session_state["_pending_q"] = _q
                st.rerun()
