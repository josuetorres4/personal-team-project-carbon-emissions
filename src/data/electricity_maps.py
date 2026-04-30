"""
Electricity Maps Carbon Intensity Connector
===========================================
Fetches hourly grid carbon intensity for all 5 supported AWS regions via the
Electricity Maps API (https://api.electricitymap.org/v3/).

Why this exists:
  The original system used three different sources (EIA for US, ENTSO-E for EU,
  Ember static for India) with different schemas, auth methods, and reliability.
  Electricity Maps gives uniform coverage of all 5 regions through one API,
  one schema, one token. EIA stays as a documented secondary source for the US.

Endpoints used:
  GET /v3/carbon-intensity/history?zone={zone}    — last 24 hours hourly data

Auth:
  Header `auth-token: <token>`. Free tier requires registration at
  https://api-portal.electricitymaps.com/.

Output schema (matches src.data.carbon_intensity_real):
  timestamp | region | intensity_gco2_kwh | intensity_lower | intensity_upper | source
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from config import Config

# AWS region → Electricity Maps zone code
ZONE_MAP = {
    "us-east-1":  "US-MIDA-PJM",   # Virginia / PJM Interconnection
    "us-west-2":  "US-NW-PACW",    # Oregon / PacifiCorp West (BPA-adjacent)
    "eu-west-1":  "IE",            # Ireland
    "eu-north-1": "SE",            # Sweden (covers eu-north-1 in Stockholm)
    "ap-south-1": "IN-WE",         # India Western grid (Maharashtra/Mumbai)
}

API_BASE = "https://api.electricitymap.org/v3"
CACHE_DIR = Path("data/.cache")


def _cache_path(zone: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"em_{zone}.json"


def _is_cache_valid(path: Path) -> bool:
    if not path.exists():
        return False
    age_hours = (time.time() - path.stat().st_mtime) / 3600
    return age_hours < Config.CARBON_DATA_CACHE_HOURS


def _read_cache(path: Path) -> Optional[list]:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _write_cache(path: Path, data: list):
    try:
        with open(path, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def _fetch_zone_history(zone: str, token: str) -> Optional[list]:
    """Fetch the last 24 hours of carbon intensity for one zone."""
    cp = _cache_path(zone)
    if _is_cache_valid(cp):
        cached = _read_cache(cp)
        if cached:
            return cached

    url = f"{API_BASE}/carbon-intensity/history"
    headers = {"auth-token": token}
    params = {"zone": zone}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        history = resp.json().get("history", [])
        if not history:
            print(f"  [ElectricityMaps] No history returned for {zone}")
            return None
        _write_cache(cp, history)
        return history
    except Exception as e:
        print(f"  [ElectricityMaps] Fetch failed for {zone}: {e}")
        return None


def _history_to_df(
    history: list,
    region: str,
    zone: str,
    start_date: datetime,
    num_days: int,
) -> pd.DataFrame:
    """
    Convert Electricity Maps history records into our hourly schema, tiling the
    fetched window across the full simulation period (cyclic reuse) so we don't
    hammer the API for 30 days of historical data.

    Each record has: datetime, carbonIntensity (gCO2eq/kWh), updatedAt.
    """
    if not history:
        return pd.DataFrame()

    # Sort source records by their hour-of-day so tiling produces a smooth
    # diurnal pattern when repeated across days.
    sorted_recs = sorted(
        history,
        key=lambda r: datetime.fromisoformat(r["datetime"].replace("Z", "+00:00")).hour,
    )

    rows = []
    total_hours = num_days * 24
    for h in range(total_hours):
        ts = start_date + timedelta(hours=h)
        # Pick the source record whose hour-of-day matches; fall back cyclically
        match = next(
            (r for r in sorted_recs if datetime.fromisoformat(r["datetime"].replace("Z", "+00:00")).hour == ts.hour),
            sorted_recs[h % len(sorted_recs)],
        )
        intensity = float(match.get("carbonIntensity") or 0)
        if intensity <= 0:
            # Zone returned a null/zero — skip; caller will treat region as failed
            continue
        rows.append({
            "timestamp": ts,
            "region": region,
            "intensity_gco2_kwh": round(intensity, 1),
            "intensity_lower": round(intensity * 0.9, 1),
            "intensity_upper": round(intensity * 1.1, 1),
            "source": f"Electricity Maps — {zone}",
        })

    return pd.DataFrame(rows)


def fetch_electricity_maps_intensity(
    start_date: datetime,
    num_days: int = 30,
) -> dict[str, pd.DataFrame]:
    """
    Fetch carbon intensity for all 5 regions via Electricity Maps.

    Returns a dict {region: DataFrame}. Regions with failed fetches are absent
    from the returned dict — callers decide what to do (real-only mode raises;
    legacy mode falls back).
    """
    token = Config.ELECTRICITYMAPS_API_TOKEN
    if not token:
        return {}

    out: dict[str, pd.DataFrame] = {}
    for region, zone in ZONE_MAP.items():
        history = _fetch_zone_history(zone, token)
        if not history:
            continue
        df = _history_to_df(history, region, zone, start_date, num_days)
        if len(df) > 0:
            out[region] = df
            print(f"  [ElectricityMaps] {region} ({zone}): {len(df)} hours tiled")
    return out


def get_last_fetched_per_region() -> dict[str, str]:
    """
    Return the cache-file mtime per region as an ISO-8601 string, for the
    dashboard provenance sidebar. Missing cache → 'never'.
    """
    out = {}
    for region, zone in ZONE_MAP.items():
        cp = _cache_path(zone)
        if cp.exists():
            out[region] = datetime.fromtimestamp(cp.stat().st_mtime).isoformat(timespec="seconds")
        else:
            out[region] = "never"
    return out
