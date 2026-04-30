"""
Azure VM Traces Loader
======================
Loads Azure Public Dataset VM Traces (2019) and maps them to the Job model
used by the sust-AI-naible pipeline.

Dataset: https://github.com/Azure/AzurePublicDataset
Download: wget https://azurepublicdatasettraces.blob.core.windows.net/azurepublicdatasetv2/trace_data/vmtable/vmtable.csv.gz

Columns in the Azure dataset:
  vmId, subscriptionId, deploymentId, vmCategory, vmCreated, vmDeleted,
  maxCpu, avgCpu, p95MaxCpu, vm_mem, core

Mapping heuristics are documented inline.
"""

import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from config import Config
from src.shared.models import Job, WorkloadCategory, REGIONS

# Reuse team definitions from workload generator
TEAMS = [
    "platform", "frontend", "backend-api", "data-eng", "ml-team",
    "mobile", "devops", "eu-backend", "eu-frontend", "analytics",
]

# Weighted region distribution matching realistic cloud usage
REGION_LIST = list(REGIONS.keys())
REGION_WEIGHTS = [0.40, 0.20, 0.15, 0.10, 0.15]  # us-east-1, us-west-2, eu-west-1, eu-north-1, ap-south-1


def _map_vm_category_to_sla(category: str) -> WorkloadCategory:
    """Map Azure vmCategory to WorkloadCategory."""
    cat = (category or "").lower().strip()
    if cat == "delay-insensitive":
        return WorkloadCategory.SUSTAINABLE
    elif cat == "interactive":
        return WorkloadCategory.URGENT
    else:
        return WorkloadCategory.BALANCED


def _map_to_workload_type(
    category: str,
    duration_hours: float,
    core_count: int,
    has_gpu: bool,
) -> str:
    """Map Azure VM properties to workload_type string."""
    cat = (category or "").lower().strip()

    if has_gpu:
        return "model_training"
    if cat == "delay-insensitive":
        if duration_hours > 1.0:
            return "batch_analytics"
        return "dev_test"
    if cat == "interactive":
        if duration_hours >= 20:
            return "production"
        if duration_hours < 0.5:
            return "ci_cd"
        return "production"
    # Unknown / balanced
    if duration_hours < 0.5:
        return "ci_cd"
    if duration_hours > 4:
        return "batch_analytics"
    return "dev_test"


def _assign_region(subscription_id: str, rng: np.random.Generator) -> str:
    """Deterministic region assignment based on subscription hash."""
    h = hash(str(subscription_id))
    # Use hash to seed a local RNG for deterministic but distributed assignment
    local_rng = np.random.default_rng(abs(h) % (2**31))
    return local_rng.choice(REGION_LIST, p=REGION_WEIGHTS)


def _assign_team(subscription_id: str) -> str:
    """Map subscription to one of the 10 teams deterministically."""
    h = hash(str(subscription_id))
    return TEAMS[abs(h) % len(TEAMS)]


def load_azure_traces(
    sim_start: datetime,
    sim_days: int = 30,
    seed: int = 42,
    max_jobs: Optional[int] = 30000,
) -> list[Job]:
    """
    Load Azure VM traces and convert to list[Job].

    Args:
        sim_start: Start of the simulation window
        sim_days: Number of days to simulate
        seed: Random seed for reproducibility
        max_jobs: Maximum number of jobs to load (None = all)

    Returns:
        list[Job] compatible with the existing pipeline
    """
    data_path = Path(Config.WORKLOAD_DATA_PATH)
    if not data_path.exists():
        print(f"  [Data] Azure traces file not found: {data_path}")
        return []

    print(f"  [Data] Loading Azure VM traces from {data_path}...")

    # Dataset has no header row — columns are positional
    # Order: vmId, subscriptionId, deploymentId, vmCreated, vmDeleted,
    #        maxCpu, avgCpu, p95MaxCpu, vmCategory, core, vm_mem
    COLUMN_NAMES = [
        "vmId", "subscriptionId", "deploymentId",
        "vmCreated", "vmDeleted",
        "maxCpu", "avgCpu", "p95MaxCpu",
        "vmCategory", "core", "vm_mem",
    ]
    USE_COLS = [0, 1, 2, 3, 4, 5, 6, 8, 9]  # positional indices we need

    try:
        df = pd.read_csv(
            data_path,
            header=None,
            names=COLUMN_NAMES,
            usecols=USE_COLS,
            nrows=max_jobs * 3 if max_jobs else None,  # read extra to filter
        )
    except Exception as e:
        print(f"  [Data] Failed to read Azure traces: {e}")
        return []

    print(f"  [Data] Loaded {len(df):,} raw VM records")

    # Clean data
    df = df.dropna(subset=["vmCreated", "vmDeleted"])
    df["vmCreated"] = pd.to_numeric(df["vmCreated"], errors="coerce")
    df["vmDeleted"] = pd.to_numeric(df["vmDeleted"], errors="coerce")
    df = df.dropna(subset=["vmCreated", "vmDeleted"])
    df = df[df["vmDeleted"] > df["vmCreated"]]
    df["core"] = pd.to_numeric(df["core"], errors="coerce").fillna(4).astype(int).clip(lower=1, upper=96)
    df["avgCpu"] = pd.to_numeric(df["avgCpu"], errors="coerce").fillna(50)
    df["maxCpu"] = pd.to_numeric(df["maxCpu"], errors="coerce").fillna(80)

    if len(df) == 0:
        print("  [Data] No valid VM records after cleaning")
        return []

    # Sample if needed
    if max_jobs and len(df) > max_jobs:
        df = df.sample(n=max_jobs, random_state=seed)

    print(f"  [Data] Using {len(df):,} VMs after cleaning and sampling")

    # Normalize timestamps to simulation window
    min_ts = df["vmCreated"].min()
    max_ts = df["vmDeleted"].max()
    ts_range = max(max_ts - min_ts, 1)
    sim_range_seconds = sim_days * 86400

    rng = np.random.default_rng(seed)
    jobs = []

    for _, row in df.iterrows():
        # Normalize timestamps into [sim_start, sim_start + sim_days]
        normalized_start = (row["vmCreated"] - min_ts) / ts_range * sim_range_seconds
        normalized_end = (row["vmDeleted"] - min_ts) / ts_range * sim_range_seconds
        duration_seconds = max(normalized_end - normalized_start, 120)  # min 2 minutes
        duration_hours = min(duration_seconds / 3600, 720)  # max 30 days

        started_at = sim_start + timedelta(seconds=normalized_start)
        ended_at = started_at + timedelta(hours=duration_hours)

        # Clamp to simulation window
        if started_at >= sim_start + timedelta(days=sim_days):
            continue

        core_count = int(row["core"])
        avg_cpu = float(row["avgCpu"])
        has_gpu = core_count >= 16 and avg_cpu > 80
        vm_category = str(row.get("vmCategory", "Unknown"))
        subscription_id = str(row.get("subscriptionId", ""))
        deployment_id = str(row.get("deploymentId", ""))[:8]

        job = Job(
            job_id=f"az-{row['vmId']}",
            name=f"azure-vm-{row['vmId']}",
            team_id=_assign_team(subscription_id),
            service_name=f"deploy-{deployment_id}",
            region=_assign_region(subscription_id, rng),
            vcpus=core_count,
            gpu_count=1 if has_gpu else 0,
            duration_hours=round(duration_hours, 3),
            category=_map_vm_category_to_sla(vm_category),
            started_at=started_at,
            ended_at=ended_at,
            workload_type=_map_to_workload_type(vm_category, duration_hours, core_count, has_gpu),
        )
        jobs.append(job)

    print(f"  [Data] Created {len(jobs):,} Job objects from Azure traces")
    return jobs


def _inject_production_workloads(jobs: list[Job], seed: int) -> list[Job]:
    """
    Stress-test hook: if STRESS_TEST_PRODUCTION_FRACTION is set (e.g. "0.50"),
    randomly reclassify that fraction of loaded jobs to workload_type="production".

    Why this matters: the Planner marks any recommendation for a production job
    as risk_level="high" (planner.py:397). Governance then applies its 85%
    human-simulated approval rate, producing real rejections. Single-model has
    no code-level enforcement — its fallback approves everything that saves
    carbon. This makes the architectural gap between the two pipelines visible.

    Jobs keep their original WorkloadCategory (not URGENT), so the Planner still
    considers them for optimization.
    """
    frac_str = os.getenv("STRESS_TEST_PRODUCTION_FRACTION", "")
    if not frac_str:
        return jobs
    try:
        frac = float(frac_str)
    except ValueError:
        return jobs
    if frac <= 0:
        return jobs

    rng = np.random.default_rng(seed + 9999)
    n_inject = int(len(jobs) * min(frac, 1.0))
    non_prod = [i for i, j in enumerate(jobs) if j.workload_type != "production"]
    chosen = rng.choice(non_prod, size=min(n_inject, len(non_prod)), replace=False)
    for idx in chosen:
        jobs[idx].workload_type = "production"
    print(f"  [StressTest] Reclassified {len(chosen):,} jobs → production "
          f"({frac:.0%} of {len(jobs):,} total)")
    return jobs


def get_workload_data(
    sim_start: datetime,
    sim_days: int = 30,
    seed: int = 42,
    max_jobs: Optional[int] = None,
) -> list[Job]:
    """
    Public API for the orchestrator. Returns workload data as list[Job].

    In real-data-only mode (Config.REAL_DATA_ONLY=True, default), the Azure VM
    traces CSV must exist or this raises RuntimeError. In legacy mode, falls
    back to synthetic generation.
    """
    if Config.REAL_DATA_ONLY and not Config.USE_REAL_WORKLOAD_DATA:
        raise RuntimeError(
            "REAL_DATA_ONLY=true requires USE_REAL_WORKLOAD_DATA=true. "
            "Set both env vars to enable real-data-only mode."
        )

    if Config.USE_REAL_WORKLOAD_DATA:
        data_path = Path(Config.WORKLOAD_DATA_PATH)
        if not data_path.exists():
            msg = (
                f"Real workload data missing at {data_path}. Download Azure "
                f"VM traces: wget https://azurepublicdatasettraces.blob.core."
                f"windows.net/azurepublicdatasetv2/trace_data/vmtable/"
                f"vmtable.csv.gz && gunzip vmtable.csv.gz && mkdir -p "
                f"data/azure_traces && mv vmtable.csv {data_path}"
            )
            if Config.REAL_DATA_ONLY:
                raise FileNotFoundError(f"REAL_DATA_ONLY=true — {msg}")
            print(f"  [Data] {msg}")
        else:
            print("  [Data] Loading real workload data (Azure VM Traces)...")
            effective_max = max_jobs if max_jobs is not None else int(
                os.getenv("MAX_AZURE_JOBS", "30000")
            )
            jobs = load_azure_traces(sim_start, sim_days, seed, max_jobs=effective_max)
            if jobs:
                jobs = _inject_production_workloads(jobs, seed)
                return jobs
            if Config.REAL_DATA_ONLY:
                raise RuntimeError(
                    "Azure traces loaded but produced no jobs. "
                    "CSV may be empty or malformed."
                )
            print("  [Data] Azure traces load failed, falling back to synthetic")

    from src.simulator.workload_generator import generate_workloads
    return generate_workloads(sim_start, num_days=sim_days, seed=seed)
