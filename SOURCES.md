# Sources — sust-AI-naible

All sources referenced in the CP1 presentation, with links.

---

## Academic Papers (Slide 5 — Literature)

### 1. Masanet et al. (2020) — Data center energy use
> Used in Slide 2 (the "1% of global emissions" claim) and Slide 5

- **Title:** Recalibrating global data center energy-use estimates
- **Authors:** Eric Masanet, Arman Shehabi, Nuoa Lei, Sarah Smith, Jonathan Koomey
- **Published:** *Science*, Vol. 367, Issue 6481, pp. 984–986 (Feb 2020)
- **Link:** https://www.science.org/doi/10.1126/science.aba3758
- **PDF:** https://datacenters.lbl.gov/sites/default/files/Masanet_et_al_Science_2020.full_.pdf
- **Key claim we use:** Data centers account for ~1% of global electricity use (~205 TWh in 2018)

**Reflection:** This paper provided crucial context for understanding the scale of the problem we're addressing. While 1% may seem small, it represents a significant and growing portion of global emissions, especially as cloud computing continues to expand. The paper's methodology for recalibrating estimates highlighted the importance of accurate measurement—a principle we've tried to embed in our system through uncertainty quantification and verification mechanisms. The fact that this was published in *Science* also validated that data center emissions are a legitimate scientific concern, not just a niche technical issue.

---

### 2. Radovanović et al. (2022) — Carbon-aware computing at Google
> Used in Slide 5 (the "10-40% reduction via load shifting" claim)

- **Title:** Carbon-Aware Computing for Datacenters
- **Authors:** Ana Radovanović, Ross Koningstein, Ian Schneider, Bokan Chen, et al. (Google)
- **Published:** *IEEE Transactions on Power Systems* (2022); preprint arXiv 2021
- **Link (IEEE):** https://ieeexplore.ieee.org/document/9770383
- **Link (arXiv):** https://arxiv.org/abs/2106.11750
- **Key claim we use:** Google achieved 10-40% carbon reduction by shifting flexible workloads temporally and spatially. No public verification methodology published.

**Reflection:** This paper was both inspiring and frustrating. On one hand, it demonstrated that carbon-aware computing is not just theoretical—Google has achieved real, substantial reductions. The 10-40% range showed us what's possible with proper load shifting strategies. However, the lack of public verification methodology was a key gap we identified. This directly informed our design decision to include verification and uncertainty quantification as core features. We wanted to build a system where claims could be independently verified, addressing the transparency issue we saw in industry implementations. The paper also reinforced the importance of temporal and spatial flexibility, which became central to our executor agent's decision-making logic.

---

### 3. Wu et al. (2023) — AutoGen multi-agent framework
> Used in Slide 5 (the "multi-agent > monolith" claim)

- **Title:** AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation
- **Authors:** Qingyun Wu, Gagan Bansal, Jieyu Zhang, et al. (Microsoft Research)
- **Published:** COLM 2024; Best Paper at LLM Agents Workshop, ICLR 2024
- **Link (Microsoft):** https://www.microsoft.com/en-us/research/publication/autogen-enabling-next-gen-llm-applications-via-multi-agent-conversation-framework/
- **Link (arXiv):** https://arxiv.org/abs/2308.08155
- **Key claim we use:** Multi-agent systems with role specialization outperform monolithic approaches for complex multi-step tasks

**Reflection:** This paper fundamentally shaped our architecture. The multi-agent paradigm resonated perfectly with our problem domain—carbon optimization requires planning, execution, accounting, verification, and governance, each with distinct expertise. Rather than building one monolithic system trying to do everything, we designed specialized agents (Planner, Executor, Carbon Accountant, Governance, Copilot) that collaborate through structured conversations. This approach not only improved modularity and maintainability but also allowed each agent to focus on its core competency. The paper's emphasis on conversation protocols influenced how we designed agent interactions, ensuring clear communication and accountability. While we didn't use AutoGen directly, its principles guided our agent design patterns.

---

### 4. Hanafy et al. (2023) — CarbonScaler
> Used in Slide 5 (the "carbon-only optimization causes cost spikes" claim)

- **Title:** CarbonScaler: Leveraging Cloud Workload Elasticity for Optimizing Carbon-Efficiency
- **Authors:** Walid A. Hanafy, Qianlin Liang, Noman Bashir, David Irwin, Prashant Shenoy
- **Published:** *Proceedings of the ACM on Measurement and Analysis of Computing Systems (SIGMETRICS)*, Vol. 7, No. 3 (Dec 2023)
- **Link (PDF):** https://lass.cs.umass.edu/papers/pdf/sigmetrics2024-carbonscaler.pdf
- **Link (arXiv):** https://arxiv.org/abs/2302.08681
- **GitHub:** https://github.com/umassos/CarbonScaler
- **Key claim we use:** 51% carbon savings over carbon-agnostic execution; demonstrates need for multi-objective optimization (carbon + cost + completion time)

**Reflection:** This paper was a critical reality check. While carbon reduction is important, real-world deployments can't ignore cost and performance. CarbonScaler's demonstration that carbon-only optimization can lead to cost spikes (sometimes 2-3x) validated our decision to implement multi-objective optimization from the start. The paper's focus on workload elasticity also informed our executor agent's strategies—we designed it to consider not just when and where to run workloads, but also how to scale them dynamically based on carbon intensity, cost, and deadlines. The 51% savings figure gave us a benchmark to aim for, though we recognize that actual results depend heavily on workload characteristics and regional grid mixes. The open-source nature of CarbonScaler also inspired us to make our system transparent and verifiable.

---

## Standards & Regulations (Slides 2 and 5)

### 5. GHG Protocol — Corporate Standard
> Used in Slide 5 (the "requires uncertainty reporting" claim)

- **Title:** GHG Protocol Corporate Accounting and Reporting Standard (Revised Edition)
- **Authors:** World Resources Institute (WRI) / World Business Council for Sustainable Development (WBCSD)
- **Published:** 2004, revised 2015
- **Link:** https://ghgprotocol.org/corporate-standard
- **PDF:** https://ghgprotocol.org/sites/default/files/ghgp/standards/ghg-protocol-revised.pdf
- **Scope 2 Guidance:** https://ghgprotocol.org/sites/default/files/2023-03/Scope%202%20Guidance.pdf
- **Key claim we use:** The de facto global standard requires uncertainty reporting for carbon claims; defines location-based and market-based accounting methods

---

### 6. EU CSRD — Corporate Sustainability Reporting Directive
> Used in Slide 2 (the "regulations require carbon disclosure" claim)

- **Title:** Corporate Sustainability Reporting Directive (CSRD)
- **Authority:** European Commission
- **Effective:** Phased rollout starting 2024-2025 for large companies
- **Link:** https://finance.ec.europa.eu/regulation-and-supervision/financial-services-legislation/implementing-and-delegated-acts/corporate-sustainability-reporting-directive_en
- **Key claim we use:** ~50,000 companies now legally required to report carbon emissions, including Scope 1, 2, and 3

---

## Data Sources (Used in our simulation)

### 7. EPA eGRID — US grid emissions data
> Used in our carbon intensity model (the regional gCO₂/kWh numbers)

- **Title:** Emissions & Generation Resource Integrated Database (eGRID)
- **Authority:** US Environmental Protection Agency
- **Latest:** eGRID2022 (released Jan 2024)
- **Link:** https://www.epa.gov/egrid
- **Data download:** https://www.epa.gov/egrid/download-data
- **Data explorer:** https://www.epa.gov/egrid/data-explorer
- **Key data we use:** Regional grid emission factors (lb CO₂/MWh) for US regions — converted to gCO₂/kWh for our model

---

## Tools Reviewed (Slide 4)

### 8. AWS Customer Carbon Footprint Tool
- **Link:** https://aws.amazon.com/sustainability/tools/aws-customer-carbon-footprint-tool/
- **What it does:** Monthly aggregate emissions by service, Scope 1/2/3, location-based and market-based methods
- **What it lacks:** No automation, no per-job granularity, no verification, retrospective only

### 9. Google Cloud Carbon Footprint
- **Link:** https://cloud.google.com/carbon-footprint
- **What it does:** Per-project emissions, BigQuery export, region suggestions, GHG Protocol compliant
- **What it lacks:** No automation (suggests cleaner regions but doesn't move workloads), no verification

### 10. Cloud Carbon Footprint (Open Source — Thoughtworks)
- **Link:** https://www.cloudcarbonfootprint.org/
- **GitHub:** https://github.com/cloud-carbon-footprint/cloud-carbon-footprint
- **Docs:** https://cloudcarbonfootprint.org/docs
- **What it does:** Multi-cloud (AWS, GCP, Azure), open-source, billing-based estimation, actionable recommendations
- **What it lacks:** Dashboard only, no execution, no verification, emission factors can be stale

### 11. Electricity Maps
- **Link:** https://www.electricitymaps.com/
- **API docs:** https://app.electricitymaps.com/developer-hub/api
- **Dashboard:** https://app.electricitymaps.com/dashboard
- **What it does:** Real-time carbon intensity for 350+ zones worldwide, historical data, 72h forecasts
- **What it lacks:** Signal only — doesn't integrate with schedulers, no workload awareness, no verification
- **How we use it:** Primary live carbon-intensity source for all 5 supported regions via `src/data/electricity_maps.py`. Auth via `ELECTRICITYMAPS_API_TOKEN`.

---

## Real-Data-Only Mode — Source Citations

When `REAL_DATA_ONLY=true` (default), every input is sourced from one of the
following — no synthetic fallback is permitted:

| Input | Source | Mechanism |
|---|---|---|
| Carbon intensity | Electricity Maps (primary) | Live API, 6-hour cache |
| Carbon intensity (US fallback) | EIA Open Data API v2 | Fuel-mix → gCO2/kWh, tiled |
| Carbon intensity (EU fallback) | ENTSO-E Transparency | A75 generation by type |
| Carbon intensity (India baseline) | Ember Climate 2023 | Cited annual avg + diurnal variation |
| Per-fuel emission factors | IPCC AR6 Annex III + EPA eGRID 2023 | Static, cited in code |
| Workload data | Azure Public Dataset VM Traces 2019 | One-time CSV download |
| Cloud pricing | AWS On-Demand snapshot 2025-01-15 | Cited static lookup; live path stubbed in `src/data/aws_pricing.py` |
| LLM energy estimate | Patterson et al. 2021 / Luccioni et al. 2023 | Static per-token figure, cited in dashboard |
