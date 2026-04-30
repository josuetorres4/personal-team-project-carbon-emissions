"""
Cloud Cost Model
================
Maps (region, resource_type) → $/hour using cited AWS On-Demand price snapshots.

Provenance:
  Per-vCPU rates derived from m5.large On-Demand Linux pricing (2 vCPU, 8 GiB)
  divided by 2, snapshotted from https://aws.amazon.com/ec2/pricing/on-demand/
  on 2025-01-15. GPU rates from g4dn.xlarge (1× T4) for the same date. Egress
  rates from https://aws.amazon.com/ec2/pricing/on-demand/#Data_Transfer.

Scaling to live data:
  See src/data/aws_pricing.py for the documented stub interface that swaps
  these tables for the AWS Pricing List API. The schema (`pricing_source`
  column on recommendations.csv / executions.csv) is forward-compatible with
  a live source — only the values change.
"""

PRICING_SOURCE = (
    "AWS On-Demand Pricing snapshot 2025-01-15 "
    "(m5.large / g4dn.xlarge Linux, public pricing pages)"
)

# ── Pricing tables ────────────────────────────────────────────────────
# $/hour per vCPU — derived from m5.large On-Demand Linux (2025-01-15)
VCPU_COST_PER_HOUR = {
    "us-east-1":  0.0480,   # Virginia — m5.large $0.096 / 2 vCPU
    "us-west-2":  0.0480,   # Oregon — same as us-east-1
    "eu-west-1":  0.0535,   # Ireland — m5.large $0.107 / 2 vCPU
    "eu-north-1": 0.0510,   # Stockholm — m5.large $0.102 / 2 vCPU
    "ap-south-1": 0.0470,   # Mumbai — m5.large $0.094 / 2 vCPU
}

# $/hour per GPU — derived from g4dn.xlarge (1× NVIDIA T4) Linux On-Demand
GPU_COST_PER_HOUR = {
    "us-east-1":  0.526,
    "us-west-2":  0.526,
    "eu-west-1":  0.587,
    "eu-north-1": 0.579,
    "ap-south-1": 0.681,
}

# Cross-region data transfer ($/GB egress)
# Known: AWS charges $0.01-0.09/GB for cross-region transfer
EGRESS_COST_PER_GB = {
    ("same", "same"):       0.00,    # Same region — free
    ("NA", "NA"):           0.02,    # Within North America
    ("EU", "EU"):           0.02,    # Within Europe
    ("NA", "EU"):           0.05,    # Cross-Atlantic
    ("EU", "NA"):           0.05,
    ("NA", "AS"):           0.08,    # US to Asia
    ("AS", "NA"):           0.08,
    ("EU", "AS"):           0.07,    # Europe to Asia
    ("AS", "EU"):           0.07,
}

# Average data per job by workload type (GB) — Assumption
DATA_PER_JOB_GB = {
    "ci_cd":            2,
    "batch_analytics": 50,
    "model_training":  20,
    "dev_test":         1,
    "production":       5,
}


def compute_job_cost(
    region: str,
    vcpus: int,
    gpu_count: int,
    duration_hours: float,
) -> float:
    """
    Compute the cloud cost for a job (compute only, no egress).
    
    Returns: cost in USD
    """
    vcpu_rate = VCPU_COST_PER_HOUR.get(region, 0.045)
    gpu_rate = GPU_COST_PER_HOUR.get(region, 0.80)

    cost = (vcpus * vcpu_rate + gpu_count * gpu_rate) * duration_hours
    return round(cost, 4)


def compute_egress_cost(
    from_region: str,
    to_region: str,
    data_gb: float,
) -> float:
    """
    Compute the data transfer cost for moving a workload between regions.
    
    Returns: egress cost in USD
    """
    from src.shared.models import REGIONS

    if from_region == to_region:
        return 0.0

    from_continent = REGIONS.get(from_region, {}).get("continent", "NA")
    to_continent = REGIONS.get(to_region, {}).get("continent", "NA")

    rate = EGRESS_COST_PER_GB.get(
        (from_continent, to_continent),
        0.05  # Default fallback
    )

    return round(data_gb * rate, 4)


def compute_total_cost(
    region: str,
    vcpus: int,
    gpu_count: int,
    duration_hours: float,
    original_region: str = "",
    workload_type: str = "ci_cd",
) -> dict:
    """
    Compute total cost including compute + egress (if region changed).
    
    Returns:
        {"compute_cost": float, "egress_cost": float, "total_cost": float}
    """
    compute = compute_job_cost(region, vcpus, gpu_count, duration_hours)

    egress = 0.0
    if original_region and original_region != region:
        data_gb = DATA_PER_JOB_GB.get(workload_type, 5)
        egress = compute_egress_cost(original_region, region, data_gb)

    return {
        "compute_cost": compute,
        "egress_cost": egress,
        "total_cost": round(compute + egress, 4),
    }


# ── Quick self-test ───────────────────────────────────────────────────
if __name__ == "__main__":
    print("Cost model examples:")
    print()

    # CI/CD job: 4 vCPUs, 12 min, us-east-1
    c1 = compute_total_cost("us-east-1", vcpus=4, gpu_count=0, duration_hours=0.2)
    print(f"CI/CD (us-east-1, 4 vCPU, 12min): ${c1['total_cost']:.4f}")

    # Same job in eu-north-1 (moved)
    c2 = compute_total_cost("eu-north-1", vcpus=4, gpu_count=0, duration_hours=0.2,
                            original_region="us-east-1", workload_type="ci_cd")
    print(f"CI/CD (→eu-north-1, moved):        ${c2['total_cost']:.4f} "
          f"(compute: ${c2['compute_cost']:.4f}, egress: ${c2['egress_cost']:.4f})")

    # Model training: 8 vCPUs + 1 GPU, 6 hours
    c3 = compute_total_cost("us-east-1", vcpus=8, gpu_count=1, duration_hours=6.0)
    print(f"Training (us-east-1, 8vCPU+1GPU, 6hr): ${c3['total_cost']:.2f}")

    c4 = compute_total_cost("us-west-2", vcpus=8, gpu_count=1, duration_hours=6.0,
                            original_region="us-east-1", workload_type="model_training")
    print(f"Training (→us-west-2, moved):           ${c4['total_cost']:.2f} "
          f"(compute: ${c4['compute_cost']:.2f}, egress: ${c4['egress_cost']:.2f})")
