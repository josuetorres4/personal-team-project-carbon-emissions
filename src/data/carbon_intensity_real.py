"""
Real Carbon Intensity Data Fetcher
===================================
Fetches real grid carbon intensity from multiple sources:
  - US regions: EIA Open Data API (hourly fuel mix → gCO₂/kWh)
  - EU regions: ENTSO-E Transparency Platform (hourly generation by type)
  - India:      Ember Climate static annual average with simulated variation

Falls back to synthetic data (src/simulator/carbon_intensity) when API keys
are missing or requests fail.
"""

import json
import hashlib
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests

from config import Config

# ── Region → source mapping ──────────────────────────────────────────

# EIA balancing authority codes for US regions
EIA_REGION_MAP = {
    "us-east-1": "PJM",     # Virginia — PJM Interconnection
    "us-west-2": "BPAT",    # Oregon — Bonneville Power Administration
}

# ENTSO-E bidding zone codes for EU regions
ENTSOE_REGION_MAP = {
    "eu-west-1": "10Y1001A1001A016",   # Ireland / SEM
    "eu-north-1": "10YSE-1--------K",  # Sweden (SE)
}

# Ember static regions (annual average, no API needed)
EMBER_REGION_MAP = {
    "ap-south-1": {
        "intensity": 700,       # gCO₂/kWh — India 2023 (Ember)
        "source": "Ember Climate 2023 — India annual average",
    },
}

# Standard emission factors (gCO₂/kWh) by fuel type for fuel-mix conversion
EMISSION_FACTORS = {
    # Fossil
    "coal": 995, "COL": 995,
    "natural gas": 410, "NG": 410, "gas": 410,
    "petroleum": 840, "OIL": 840, "oil": 840, "OTH": 400,
    # Zero-carbon
    "nuclear": 0, "NUC": 0,
    "hydro": 0, "WAT": 0, "hydroelectric": 0,
    "wind": 0, "WND": 0,
    "solar": 0, "SUN": 0,
    "other renewables": 0, "geothermal": 0,
    # Default for unknown
    "other": 400,
}

CACHE_DIR = Path("data/.cache")


# ── Cache helpers ─────────────────────────────────────────────────────

def _cache_path(key: str) -> Path:
    """Return a cache file path for a given key."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe_key = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"carbon_{safe_key}.json"


def _is_cache_valid(path: Path) -> bool:
    """Check if cache file exists and is fresher than CARBON_DATA_CACHE_HOURS."""
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


# ── EIA fetcher (US regions) ─────────────────────────────────────────

def _fetch_eia_intensity(
    region: str,
    start: datetime,
    end: datetime,
    api_key: str,
) -> Optional[pd.DataFrame]:
    """
    Fetch hourly fuel-type generation from EIA API v2 and convert to gCO₂/kWh.
    """
    ba_code = EIA_REGION_MAP.get(region)
    if not ba_code or not api_key:
        return None

    cache_key = f"eia_{ba_code}_{start.date()}_{end.date()}"
    cp = _cache_path(cache_key)
    cached = None
    if _is_cache_valid(cp):
        cached = _read_cache(cp)
    if cached:
        return _eia_records_to_df(cached, region)

    # EIA API v2: electricity/rto/fuel-type-data
    # Limit to last 1 day of the range to avoid large API responses
    fetch_start = max(start, end - timedelta(days=1))
    url = "https://api.eia.gov/v2/electricity/rto/fuel-type-data/data/"
    params = {
        "api_key": api_key,
        "frequency": "hourly",
        "data[0]": "value",
        "facets[respondent][]": ba_code,
        "start": fetch_start.strftime("%Y-%m-%dT%H"),
        "end": end.strftime("%Y-%m-%dT%H"),
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": 200,
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json().get("response", {}).get("data", [])
        if not data:
            print(f"  [EIA] No data returned for {ba_code}")
            return None
        _write_cache(cp, data)
        return _eia_records_to_df(data, region)
    except Exception as e:
        print(f"  [EIA] Fetch failed for {region}: {e}")
        return None


def _eia_records_to_df(records: list, region: str) -> pd.DataFrame:
    """Convert EIA fuel-type records into hourly intensity DataFrame."""
    # Group by period (hour), sum generation by fuel type, compute weighted intensity
    hourly = {}
    for rec in records:
        period = rec.get("period", "")
        fuel = rec.get("fueltype", "other")
        mwh = float(rec.get("value", 0) or 0)
        if period not in hourly:
            hourly[period] = {"total_mwh": 0, "total_co2": 0}
        ef = EMISSION_FACTORS.get(fuel, EMISSION_FACTORS.get("other", 400))
        hourly[period]["total_mwh"] += mwh
        hourly[period]["total_co2"] += mwh * ef

    rows = []
    for period, vals in sorted(hourly.items()):
        if vals["total_mwh"] > 0:
            intensity = vals["total_co2"] / vals["total_mwh"]
        else:
            intensity = 400  # fallback
        try:
            ts = datetime.strptime(period, "%Y-%m-%dT%H")
        except ValueError:
            continue
        rows.append({
            "timestamp": ts,
            "region": region,
            "intensity_gco2_kwh": round(intensity, 1),
            "intensity_lower": round(intensity * 0.9, 1),
            "intensity_upper": round(intensity * 1.1, 1),
            "source": f"EIA API — {EIA_REGION_MAP[region]}",
        })
    return pd.DataFrame(rows)


# ── ENTSO-E fetcher (EU regions) ─────────────────────────────────────

def _fetch_entsoe_intensity(
    region: str,
    start: datetime,
    end: datetime,
    token: str,
) -> Optional[pd.DataFrame]:
    """
    Fetch generation per type from ENTSO-E and convert to gCO₂/kWh.
    """
    zone = ENTSOE_REGION_MAP.get(region)
    if not zone or not token:
        return None

    cache_key = f"entsoe_{zone}_{start.date()}_{end.date()}"
    cp = _cache_path(cache_key)
    cached = None
    if _is_cache_valid(cp):
        cached = _read_cache(cp)
    if cached:
        return _entsoe_records_to_df(cached, region)

    # ENTSO-E REST API — Actual Generation per Type (A75)
    url = "https://web-api.tp.entsoe.eu/api"
    params = {
        "securityToken": token,
        "documentType": "A75",
        "processType": "A16",
        "in_Domain": zone,
        "periodStart": start.strftime("%Y%m%d%H00"),
        "periodEnd": end.strftime("%Y%m%d%H00"),
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        # Parse XML response into hourly records
        records = _parse_entsoe_xml(resp.text, start)
        if not records:
            print(f"  [ENTSO-E] No data parsed for {region}")
            return None
        _write_cache(cp, records)
        return _entsoe_records_to_df(records, region)
    except Exception as e:
        print(f"  [ENTSO-E] Fetch failed for {region}: {e}")
        return None


def _parse_entsoe_xml(xml_text: str, start: datetime) -> list:
    """Parse ENTSO-E generation XML into list of {period, fuel, mwh} dicts."""
    import xml.etree.ElementTree as ET

    records = []
    try:
        root = ET.fromstring(xml_text)
        ns = {"ns": "urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0"}

        for ts in root.findall(".//ns:TimeSeries", ns):
            psr_type_el = ts.find(".//ns:MktPSRType/ns:psrType", ns)
            psr_type = psr_type_el.text if psr_type_el is not None else "unknown"

            # Map ENTSO-E PSR types to fuel categories
            fuel = _entsoe_psr_to_fuel(psr_type)

            for period in ts.findall(".//ns:Period", ns):
                start_el = period.find("ns:timeInterval/ns:start", ns)
                res_el = period.find("ns:resolution", ns)
                if start_el is None:
                    continue
                period_start = datetime.fromisoformat(start_el.text.replace("Z", "+00:00")).replace(tzinfo=None)

                for point in period.findall("ns:Point", ns):
                    pos = int(point.find("ns:position", ns).text)
                    qty = float(point.find("ns:quantity", ns).text)
                    # Each position = 1 hour (PT60M resolution)
                    ts_hour = period_start + timedelta(hours=pos - 1)
                    records.append({
                        "period": ts_hour.strftime("%Y-%m-%dT%H"),
                        "fuel": fuel,
                        "mwh": qty,
                    })
    except Exception as e:
        print(f"  [ENTSO-E] XML parse error: {e}")

    return records


def _entsoe_psr_to_fuel(psr_type: str) -> str:
    """Map ENTSO-E PSR type code to a fuel category."""
    mapping = {
        "B01": "coal",        # Biomass (treat as low-carbon)
        "B02": "coal",        # Fossil Brown coal/Lignite
        "B03": "coal",        # Fossil Coal-derived gas
        "B04": "gas",         # Fossil Gas
        "B05": "coal",        # Fossil Hard coal
        "B06": "oil",         # Fossil Oil
        "B07": "oil",         # Fossil Oil shale
        "B08": "coal",        # Fossil Peat
        "B09": "geothermal",  # Geothermal
        "B10": "hydro",       # Hydro Pumped Storage
        "B11": "hydro",       # Hydro Run-of-river
        "B12": "hydro",       # Hydro Water Reservoir
        "B13": "other",       # Marine
        "B14": "nuclear",     # Nuclear
        "B15": "other",       # Other renewable
        "B16": "solar",       # Solar
        "B17": "other",       # Waste
        "B18": "wind",        # Wind Offshore
        "B19": "wind",        # Wind Onshore
        "B20": "other",       # Other
    }
    return mapping.get(psr_type, "other")


def _entsoe_records_to_df(records: list, region: str) -> pd.DataFrame:
    """Convert ENTSO-E fuel records into hourly intensity DataFrame."""
    hourly = {}
    for rec in records:
        period = rec["period"]
        fuel = rec["fuel"]
        mwh = rec["mwh"]
        if period not in hourly:
            hourly[period] = {"total_mwh": 0, "total_co2": 0}
        ef = EMISSION_FACTORS.get(fuel, 400)
        hourly[period]["total_mwh"] += mwh
        hourly[period]["total_co2"] += mwh * ef

    rows = []
    for period, vals in sorted(hourly.items()):
        intensity = vals["total_co2"] / vals["total_mwh"] if vals["total_mwh"] > 0 else 300
        try:
            ts = datetime.strptime(period, "%Y-%m-%dT%H")
        except ValueError:
            continue
        rows.append({
            "timestamp": ts,
            "region": region,
            "intensity_gco2_kwh": round(intensity, 1),
            "intensity_lower": round(intensity * 0.9, 1),
            "intensity_upper": round(intensity * 1.1, 1),
            "source": f"ENTSO-E Transparency — {ENTSOE_REGION_MAP[region]}",
        })
    return pd.DataFrame(rows)


# ── Ember static (India) ─────────────────────────────────────────────

def _get_ember_static(
    region: str,
    start: datetime,
    num_days: int,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Generate hourly intensity for India using Ember's annual average
    with simulated diurnal variation (±50 gCO₂/kWh sinusoidal).
    """
    profile = EMBER_REGION_MAP.get(region)
    if not profile:
        return pd.DataFrame()

    rng = np.random.default_rng(seed)
    base = profile["intensity"]
    source = profile["source"]
    rows = []

    for hour_offset in range(num_days * 24):
        ts = start + timedelta(hours=hour_offset)
        # Diurnal variation: peak at 19:30 IST (14:00 UTC)
        phase = 2 * np.pi * (ts.hour - 14) / 24
        variation = 50 * np.cos(phase)
        noise = rng.normal(0, 20)
        intensity = max(500, base + variation + noise)

        rows.append({
            "timestamp": ts,
            "region": region,
            "intensity_gco2_kwh": round(intensity, 1),
            "intensity_lower": round(intensity * 0.9, 1),
            "intensity_upper": round(intensity * 1.1, 1),
            "source": source,
        })

    return pd.DataFrame(rows)


# ── Tiling helper ─────────────────────────────────────────────────────

def _tile_to_period(
    df: pd.DataFrame,
    region: str,
    start_date: datetime,
    num_days: int,
) -> pd.DataFrame:
    """
    Repeat a short fetch (e.g. 1 day) across the full simulation period.
    Reuses the hourly pattern cyclically so we don't hammer the API for 30 days.
    """
    total_hours = num_days * 24
    if len(df) >= total_hours:
        return df.head(total_hours)

    # Build hourly timestamps for the full period
    rows = []
    source_rows = df.to_dict("records")
    for h in range(total_hours):
        ts = start_date + timedelta(hours=h)
        src = source_rows[h % len(source_rows)]
        rows.append({
            "timestamp": ts,
            "region": region,
            "intensity_gco2_kwh": src["intensity_gco2_kwh"],
            "intensity_lower": src["intensity_lower"],
            "intensity_upper": src["intensity_upper"],
            "source": src["source"],
        })
    return pd.DataFrame(rows)


# ── Public API ────────────────────────────────────────────────────────

def fetch_real_intensity(
    start_date: datetime,
    num_days: int = 30,
    seed: int = 42,
) -> Optional[pd.DataFrame]:
    """
    Fetch real carbon intensity for all 5 regions from their respective sources.
    Returns None if critical regions fail (triggering full fallback).
    """
    eia_key = Config.EIA_API_KEY if hasattr(Config, "EIA_API_KEY") else os.getenv("EIA_API_KEY", "")
    entsoe_token = Config.ENTSOE_API_TOKEN if hasattr(Config, "ENTSOE_API_TOKEN") else os.getenv("ENTSOE_API_TOKEN", "")
    end_date = start_date + timedelta(days=num_days)

    all_dfs = []
    failed_regions = []

    # US regions (EIA) — fetch a small window, then tile across full period
    for region in EIA_REGION_MAP:
        df = _fetch_eia_intensity(region, start_date, end_date, eia_key)
        if df is not None and len(df) > 0:
            df = _tile_to_period(df, region, start_date, num_days)
            all_dfs.append(df)
            print(f"  [Data] {region}: {len(df)} hours from EIA (tiled)")
        else:
            failed_regions.append(region)

    # EU regions (ENTSO-E)
    for region in ENTSOE_REGION_MAP:
        df = _fetch_entsoe_intensity(region, start_date, end_date, entsoe_token)
        if df is not None and len(df) > 0:
            df = _tile_to_period(df, region, start_date, num_days)
            all_dfs.append(df)
            print(f"  [Data] {region}: {len(df)} hours from ENTSO-E (tiled)")
        else:
            failed_regions.append(region)

    # India (Ember static)
    for region in EMBER_REGION_MAP:
        df = _get_ember_static(region, start_date, num_days, seed)
        if len(df) > 0:
            all_dfs.append(df)
            print(f"  [Data] {region}: {len(df)} hours from Ember (static + variation)")

    if failed_regions:
        print(f"  [Data] Failed regions: {failed_regions} — using synthetic fallback for these")
        # Generate synthetic for failed regions only
        from src.simulator.carbon_intensity import generate_intensity_timeseries
        synthetic_df = generate_intensity_timeseries(start_date, num_days=num_days, seed=seed)
        for region in failed_regions:
            region_df = synthetic_df[synthetic_df["region"] == region].copy()
            region_df["source"] = region_df["source"] + " (synthetic fallback)"
            all_dfs.append(region_df)

    if not all_dfs:
        return None

    result = pd.concat(all_dfs, ignore_index=True)
    return result.sort_values(["timestamp", "region"]).reset_index(drop=True)


def get_carbon_intensity_data(
    start_date: datetime,
    num_days: int = 30,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Public API for the orchestrator. Returns carbon intensity DataFrame
    in the standard schema. Uses real data if configured, else synthetic.
    """
    if Config.USE_REAL_CARBON_DATA:
        print("  [Data] Attempting to fetch real carbon intensity data...")
        df = fetch_real_intensity(start_date, num_days, seed)
        if df is not None and len(df) > 0:
            return df
        print("  [Data] Real data fetch failed entirely, falling back to synthetic")

    from src.simulator.carbon_intensity import generate_intensity_timeseries
    return generate_intensity_timeseries(start_date, num_days=num_days, seed=seed)
