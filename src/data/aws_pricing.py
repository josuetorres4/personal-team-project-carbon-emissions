"""
AWS Pricing API Connector — Stub
================================
Documented interface for fetching live AWS EC2 On-Demand prices. Not wired into
the cost model yet; src/simulator/cost_model.py uses cited static snapshots.

When you're ready to go live:
  1. Set AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (the Pricing API requires
     auth even though pricing data is public).
  2. Implement fetch_vcpu_price() and fetch_gpu_price() below.
  3. In src/simulator/cost_model.py, replace the static dict lookups with
     calls to these functions, cached per (region, instance_family) for the
     lifetime of one pipeline run.
  4. Update PRICING_SOURCE in cost_model.py to reflect the live source.

The schema (pricing_source column on recommendations.csv / executions.csv) is
already forward-compatible — only the values change.

Reference:
  https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/price-changes.html
  https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/region_index.json
"""

from typing import Optional


def fetch_vcpu_price(region: str, instance_family: str = "m5") -> Optional[float]:
    """
    Return $/hour per vCPU for the given region and instance family, or None
    on failure. Uses the AWS Pricing List API.

    Implementation outline (TODO):
      1. GET https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/
         current/{region_code}/index.json
      2. Filter products by attributes: instanceFamily=={instance_family},
         operatingSystem=Linux, tenancy=Shared, capacitystatus=Used,
         preInstalledSw=NA.
      3. Find the OnDemand term, extract pricePerUnit.USD.
      4. Divide by vCPU count from product attributes.
    """
    raise NotImplementedError(
        "Live AWS pricing not yet implemented — see module docstring for the "
        "swap path. Use src.simulator.cost_model.VCPU_COST_PER_HOUR for now."
    )


def fetch_gpu_price(region: str, instance_family: str = "g4dn") -> Optional[float]:
    """
    Return $/hour per GPU for the given region and instance family, or None
    on failure. Same Pricing List API; filter on GPU-bearing instance
    families and divide the OnDemand price by the GPU count.
    """
    raise NotImplementedError(
        "Live AWS pricing not yet implemented — see module docstring for the "
        "swap path. Use src.simulator.cost_model.GPU_COST_PER_HOUR for now."
    )


def fetch_egress_price(from_region: str, to_region: str) -> Optional[float]:
    """
    Return $/GB egress between two regions. AWS publishes a separate price
    list for Data Transfer; structure differs from EC2.
    """
    raise NotImplementedError(
        "Live AWS pricing not yet implemented — use "
        "src.simulator.cost_model.EGRESS_COST_PER_GB for now."
    )
