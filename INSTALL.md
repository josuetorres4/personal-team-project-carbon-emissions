# Installation & Setup Guide

## Prerequisites

- Python 3.11+
- pip
- Git

## Quick Start

```bash
# 1. Clone the repository
git clone <repo-url>
cd team-project-carbon-emissions

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your API keys (see below)

# 5. Run the pipeline
python run_pipeline.py

# 6. Launch the dashboard
streamlit run dashboard.py
```

## API Keys Setup

### Groq LLM (Required for live AI reasoning)

1. Go to [console.groq.com](https://console.groq.com)
2. Sign up (free tier available)
3. Create an API key
4. Add to `.env`:
   ```
   GROQ_API_KEY=gsk_your_key_here
   LLM_PROVIDER=auto
   ```

Without a Groq key, the system runs with a built-in mock LLM that produces structured, contextually appropriate responses for demo purposes.

### EIA Open Data (US carbon intensity - real data)

1. Go to [eia.gov/opendata](https://www.eia.gov/opendata/)
2. Register for a free API key (instant approval)
3. Add to `.env`:
   ```
   EIA_API_KEY=your_key_here
   USE_REAL_CARBON_DATA=true
   ```

This provides real hourly carbon intensity data for US regions (us-east-1/Virginia via PJM, us-west-2/Oregon via BPA).

### ENTSO-E Transparency Platform (EU carbon intensity - real data)

1. Go to [transparency.entsoe.eu](https://transparency.entsoe.eu/)
2. Register for a free account
3. Request a Security Token from your account settings
4. Add to `.env`:
   ```
   ENTSOE_API_TOKEN=your_token_here
   ```

This provides real hourly carbon intensity for EU regions (eu-west-1/Ireland, eu-north-1/Stockholm).

India (ap-south-1) uses Ember Climate annual average data (~700 gCO2/kWh) with simulated hourly variation. No API key needed.

### Azure VM Traces (Real workload data)

1. Download the VM traces CSV:
   ```bash
   wget https://azurepublicdatasettraces.blob.core.windows.net/azurepublicdatasetv2/trace_data/vmtable/vmtable.csv.gz
   gunzip vmtable.csv.gz
   mkdir -p data/azure_traces
   mv vmtable.csv data/azure_traces/
   ```
2. Enable in `.env`:
   ```
   USE_REAL_WORKLOAD_DATA=true
   WORKLOAD_DATA_PATH=data/azure_traces/vmtable.csv
   ```

Without the Azure traces, the system generates realistic synthetic workloads for a ~100 developer organization.

## Running

```bash
# Run the full pipeline (generates all data files)
python run_pipeline.py

# Launch the interactive dashboard
streamlit run dashboard.py

# Run tests
pytest tests/
```

## Deploy to Streamlit Cloud

1. Push your repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) and click "New app"
3. Select your repo, branch, and `dashboard.py` as the main file
4. Add secrets in Settings > Secrets:
   ```toml
   GROQ_API_KEY = "gsk_..."
   LLM_PROVIDER = "auto"
   EIA_API_KEY = "..."
   USE_REAL_CARBON_DATA = "true"
   ```
5. The app reads `requirements.txt` automatically
6. Pre-generated `data/` files serve as immediate fallback if pipeline hasn't run on the server

## Project Structure

```
team-project-carbon-emissions/
├── run_pipeline.py          # Main entry point
├── dashboard.py             # Streamlit dashboard (12 pages)
├── config.py                # Centralized configuration
├── .env.example             # Environment template
├── src/
│   ├── agents/              # AI agents (Planner, Governance, Executor, Copilot)
│   ├── data/                # Real data connectors (EIA, ENTSO-E, Azure traces)
│   ├── shared/              # Shared models, protocol, impact calculations
│   └── simulator/           # Synthetic data generators (fallback)
├── prompts/                 # Extracted system prompts for each agent
├── docs/                    # Architecture, use cases, safety, telemetry
├── tests/                   # Test suite
└── data/                    # Pipeline outputs (CSV, JSON)
```
