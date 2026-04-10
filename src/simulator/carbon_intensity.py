"""
Carbon Intensity Simulator
==========================
Generates realistic-ish hourly grid carbon intensity (gCO₂/kWh) for each region.

This replaces what WattTime or Electricity Maps would provide in a real system.
We use sinusoidal patterns + noise to mimic real grid behavior:
  - Solar-heavy regions are cleaner during midday
  - Wind-heavy regions have more random variation
  - Base load differs dramatically by region (30 to 700 gCO₂/kWh)

All numbers are Assumptions unless marked Known.
Sources we'd use in production: EPA eGRID, Electricity Maps, WattTime API.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional


# ── Region carbon profiles ────────────────────────────────────────────
# base_intensity: annual average gCO₂/kWh (Known — from EPA eGRID 2022, Electricity Maps)
# amplitude: how much it swings due to renewables (Assumption)
# noise_std: random variation (Assumption)
# peak_hour: hour (UTC) when intensity is HIGHEST (less renewables)
#   - For solar regions: peak at night (~22:00 local)
#   - For wind regions: less predictable, smaller amplitude

REGION_PROFILES = {
    "us-east-1": {   # Virginia — PJM grid, coal+gas heavy
        "base_intensity": 350,
        "amplitude": 80,       # Some solar, moderate swing
        "noise_std": 30,
        "peak_hour_utc": 3,    # ~10pm ET (night, no solar)
        "source": "EPA eGRID 2022 — PJM region",
    },
    "us-west-2": {   # Oregon — BPA grid, hydro-dominated
        "base_intensity": 90,
        "amplitude": 20,       # Hydro is steady, small swing
        "noise_std": 15,
        "peak_hour_utc": 6,    # ~10pm PT
        "source": "EPA eGRID 2022 — NWPP region",
    },
    "eu-west-1": {   # Ireland — wind-heavy, variable
        "base_intensity": 300,
        "amplitude": 100,      # Wind makes it swing a lot
        "noise_std": 50,
        "peak_hour_utc": 18,   # ~6pm local (evening demand, less wind sometimes)
        "source": "EirGrid 2023 data",
    },
    "eu-north-1": {  # Stockholm — hydro + nuclear, very clean
        "base_intensity": 30,
        "amplitude": 10,       # Very stable
        "noise_std": 5,
        "peak_hour_utc": 17,
        "source": "Swedish Energy Agency 2023",
    },
    "ap-south-1": {  # Mumbai — coal-heavy, dirty
        "base_intensity": 700,
        "amplitude": 50,       # Coal is steady (unfortunately)
        "noise_std": 40,
        "peak_hour_utc": 14,   # ~7:30pm IST (evening peak)
        "source": "CEA India 2022",
    },
}


def generate_intensity_timeseries(
    start_date: datetime,
    num_days: int = 30,
    resolution_hours: int = 1,
    seed: Optional[int] = 42,
) -> pd.DataFrame:
    """
    Generate hourly carbon intensity for all regions over a time period.
    
    Returns:
        DataFrame with columns: [timestamp, region, intensity_gco2_kwh, 
                                  intensity_lower, intensity_upper, source]
    """
    if seed is not None:
        rng = np.random.default_rng(seed)
    else:
        rng = np.random.default_rng()

    total_hours = num_days * 24 // resolution_hours
    timestamps = [start_date + timedelta(hours=h * resolution_hours) for h in range(total_hours)]

    rows = []
    for region, profile in REGION_PROFILES.items():
        base = profile["base_intensity"]
        amp = profile["amplitude"]
        noise_std = profile["noise_std"]
        peak_hour = profile["peak_hour_utc"]

        for i, ts in enumerate(timestamps):
            hour_of_day = ts.hour
            # Sinusoidal pattern: peak at peak_hour, trough 12 hours later
            phase = 2 * np.pi * (hour_of_day - peak_hour) / 24
            seasonal = amp * np.cos(phase)

            # Day-to-day variation (weather, demand shifts)
            daily_drift = 20 * np.sin(2 * np.pi * (ts.timetuple().tm_yday / 365))

            # Random noise
            noise = rng.normal(0, noise_std)

            # Final intensity (clamp to reasonable range)
            intensity = max(5, base + seasonal + daily_drift + noise)

            # Uncertainty bounds (±20% is Assumption — real uncertainty varies)
            uncertainty_pct = 0.20
            lower = intensity * (1 - uncertainty_pct)
            upper = intensity * (1 + uncertainty_pct)

            rows.append({
                "timestamp": ts,
                "region": region,
                "intensity_gco2_kwh": round(intensity, 1),
                "intensity_lower": round(lower, 1),
                "intensity_upper": round(upper, 1),
                "source": profile["source"],
            })

    df = pd.DataFrame(rows)
    return df.sort_values(["timestamp", "region"]).reset_index(drop=True)


def get_intensity_at(
    intensity_df: pd.DataFrame,
    region: str,
    timestamp: datetime,
) -> dict:
    """
    Look up the carbon intensity for a specific region and time.
    Returns the nearest hourly value (rounds down).
    
    Returns:
        {"intensity": float, "lower": float, "upper": float, "source": str}
    """
    # Round timestamp down to nearest hour
    ts_hour = timestamp.replace(minute=0, second=0, microsecond=0)

    mask = (intensity_df["region"] == region) & (intensity_df["timestamp"] == ts_hour)
    matches = intensity_df[mask]

    if matches.empty:
        # Fallback to region average if exact timestamp not found
        profile = REGION_PROFILES.get(region, {"base_intensity": 400, "source": "fallback"})
        return {
            "intensity": profile["base_intensity"],
            "lower": profile["base_intensity"] * 0.8,
            "upper": profile["base_intensity"] * 1.2,
            "source": f"{profile.get('source', 'unknown')} (fallback — no exact match)",
        }

    row = matches.iloc[0]
    return {
        "intensity": row["intensity_gco2_kwh"],
        "lower": row["intensity_lower"],
        "upper": row["intensity_upper"],
        "source": row["source"],
    }


# ── Quick self-test ───────────────────────────────────────────────────
if __name__ == "__main__":
    print("Generating 30-day carbon intensity time series...")
    df = generate_intensity_timeseries(datetime(2025, 1, 1), num_days=30)
    
    print(f"\nGenerated {len(df):,} data points")
    print(f"Regions: {df['region'].unique().tolist()}")
    print(f"Time range: {df['timestamp'].min()} → {df['timestamp'].max()}")
    print(f"\nAverage intensity by region (gCO₂/kWh):")
    print(df.groupby("region")["intensity_gco2_kwh"].agg(["mean", "min", "max"]).round(1))
    
    # Quick sanity check
    sample = get_intensity_at(df, "us-west-2", datetime(2025, 1, 15, 14, 30))
    print(f"\nSample lookup — us-west-2 at 2025-01-15 14:30 UTC:")
    print(f"  Intensity: {sample['intensity']} gCO₂/kWh [{sample['lower']}–{sample['upper']}]")
