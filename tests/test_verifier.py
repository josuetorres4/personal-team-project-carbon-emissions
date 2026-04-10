"""
Tests for the Verifier Agent — the core MRV (Measurement, Reporting, Verification)
differentiator of the sust-AI-naible system.

Covers: counterfactual logic, CI bounds, SLA compliance, batch edge cases, evidence chains.
"""

import pytest
import pandas as pd
from datetime import datetime, timedelta

from src.shared.models import Job, Recommendation, VerificationRecord, WorkloadCategory
from src.agents.verifier import verify_single, verify_batch, summarize_verification, _hash_inputs
from src.agents.carbon_accountant import TDP_PER_VCPU_KW, GPU_TDP_KW, PUE


# ── Test fixtures ────────────────────────────────────────────────────

def _make_intensity_df():
    """Minimal intensity DataFrame with known values for two regions."""
    ts = datetime(2025, 1, 15, 12, 0, 0)
    rows = [
        # us-east-1: dirty region (350 gCO2/kWh, ±20%)
        {"timestamp": ts, "region": "us-east-1",
         "intensity_gco2_kwh": 350.0, "intensity_lower": 280.0, "intensity_upper": 420.0,
         "source": "test"},
        # eu-north-1: clean region (30 gCO2/kWh, ±20%)
        {"timestamp": ts, "region": "eu-north-1",
         "intensity_gco2_kwh": 30.0, "intensity_lower": 24.0, "intensity_upper": 36.0,
         "source": "test"},
        # eu-west-1: medium region (300 gCO2/kWh, ±20%)
        {"timestamp": ts, "region": "eu-west-1",
         "intensity_gco2_kwh": 300.0, "intensity_lower": 240.0, "intensity_upper": 360.0,
         "source": "test"},
    ]
    return pd.DataFrame(rows)


def _make_job(region="us-east-1", vcpus=4, gpu_count=0, duration_hours=1.0,
              category=WorkloadCategory.SUSTAINABLE, job_id="test-job-1"):
    ts = datetime(2025, 1, 15, 12, 0, 0)
    return Job(
        job_id=job_id, region=region, vcpus=vcpus, gpu_count=gpu_count,
        duration_hours=duration_hours, category=category,
        started_at=ts, team_id="team-a", workload_type="batch_analytics",
    )


def _make_recommendation(job_id="test-job-1", proposed_region="eu-north-1",
                         proposed_time=None, status="executed"):
    ts = datetime(2025, 1, 15, 12, 0, 0)
    return Recommendation(
        job_id=job_id,
        action_type="region_shift",
        current_region="us-east-1",
        proposed_region=proposed_region,
        current_time=ts,
        proposed_time=proposed_time or ts,
        est_carbon_delta_kg=-0.001,
        est_cost_delta_usd=0.01,
        confidence=0.85,
        status=status,
    )


# ── Tests ────────────────────────────────────────────────────────────

class TestVerifySingle:
    """Tests for verify_single — the core counterfactual logic."""

    def test_verify_known_savings(self):
        """Job moved from dirty region (us-east-1, 350) to clean (eu-north-1, 30).
        Savings must be positive and confirmed."""
        idf = _make_intensity_df()
        original = _make_job(region="us-east-1")
        executed = _make_job(region="eu-north-1")
        rec = _make_recommendation(proposed_region="eu-north-1")

        v = verify_single(rec, original, executed, idf)

        assert v.verified_savings_kgco2e > 0, "Savings should be positive for dirty->clean shift"
        assert v.verification_status == "confirmed", "Large intensity gap should yield confirmed status"
        assert v.ci_lower > 0, "CI lower bound should be > 0 for large gap"
        assert v.counterfactual_kgco2e > v.actual_kgco2e
        assert len(v.evidence_chain) == 7, "Evidence chain should have 7 steps"

    def test_verify_no_savings(self):
        """Same region, same time — zero savings, status refuted."""
        idf = _make_intensity_df()
        original = _make_job(region="us-east-1")
        executed = _make_job(region="us-east-1")  # same region
        rec = _make_recommendation(proposed_region="us-east-1")

        v = verify_single(rec, original, executed, idf)

        assert v.verified_savings_kgco2e == 0, "Same config should produce zero savings"
        assert v.verification_status == "refuted"

    def test_verify_partial_savings(self):
        """Close intensity values — CI should cross zero, status partial."""
        idf = _make_intensity_df()
        # us-east-1 (350 ± 20%) vs eu-west-1 (300 ± 20%)
        # Point estimate positive but CI: (280 - 360) to (420 - 240) => (-80 to 180)
        original = _make_job(region="us-east-1")
        executed = _make_job(region="eu-west-1")
        rec = _make_recommendation(proposed_region="eu-west-1")

        v = verify_single(rec, original, executed, idf)

        assert v.verified_savings_kgco2e > 0, "Point estimate should be positive"
        assert v.ci_lower < 0, "CI lower should be negative for close regions"
        assert v.verification_status == "partial"

    def test_ci_contains_point_estimate(self):
        """The point estimate must always be within the CI bounds."""
        idf = _make_intensity_df()
        test_cases = [
            ("us-east-1", "eu-north-1"),  # large gap
            ("us-east-1", "eu-west-1"),   # small gap
            ("us-east-1", "us-east-1"),   # no gap
        ]
        for orig_region, exec_region in test_cases:
            original = _make_job(region=orig_region)
            executed = _make_job(region=exec_region)
            rec = _make_recommendation(proposed_region=exec_region)
            v = verify_single(rec, original, executed, idf)
            assert v.ci_lower <= v.verified_savings_kgco2e <= v.ci_upper, (
                f"Point estimate {v.verified_savings_kgco2e} outside CI "
                f"[{v.ci_lower}, {v.ci_upper}] for {orig_region}->{exec_region}"
            )

    def test_sla_violation(self):
        """Proposed time exceeds SUSTAINABLE deferral window (24h) -> SLA violated."""
        idf = _make_intensity_df()
        ts = datetime(2025, 1, 15, 12, 0, 0)
        original = _make_job(region="us-east-1", category=WorkloadCategory.SUSTAINABLE)
        executed = _make_job(region="eu-north-1")
        # Proposed time is 48 hours later — exceeds 24h window
        rec = _make_recommendation(
            proposed_region="eu-north-1",
            proposed_time=ts + timedelta(hours=48),
        )

        v = verify_single(rec, original, executed, idf)

        assert v.sla_compliant is False, "48h delay should violate 24h SUSTAINABLE SLA"

    def test_sla_compliant_within_window(self):
        """Proposed time within deferral window -> SLA compliant."""
        idf = _make_intensity_df()
        ts = datetime(2025, 1, 15, 12, 0, 0)
        original = _make_job(region="us-east-1", category=WorkloadCategory.SUSTAINABLE)
        executed = _make_job(region="eu-north-1")
        rec = _make_recommendation(
            proposed_region="eu-north-1",
            proposed_time=ts + timedelta(hours=12),  # within 24h window
        )

        v = verify_single(rec, original, executed, idf)

        assert v.sla_compliant is True


class TestVerifyBatch:
    """Tests for verify_batch — edge cases and filtering."""

    def test_batch_skips_non_executed(self):
        """Recommendations with status != 'executed' should be skipped."""
        idf = _make_intensity_df()
        original = _make_job()
        executed = _make_job(region="eu-north-1")
        rec = _make_recommendation(status="proposed")  # not executed

        results = verify_batch([rec], [original], [executed], idf)

        assert len(results) == 0, "Non-executed recs should be skipped"

    def test_batch_handles_missing_jobs(self):
        """Recommendations referencing missing job_ids should be skipped."""
        idf = _make_intensity_df()
        rec = _make_recommendation(job_id="nonexistent-job")

        results = verify_batch([rec], [], [], idf)

        assert len(results) == 0, "Missing jobs should be skipped without error"

    def test_batch_processes_valid_recs(self):
        """Valid executed recommendations should be verified."""
        idf = _make_intensity_df()
        original = _make_job(job_id="j1", region="us-east-1")
        executed = _make_job(job_id="j1", region="eu-north-1")
        rec = _make_recommendation(job_id="j1", status="executed")

        results = verify_batch([rec], [original], [executed], idf)

        assert len(results) == 1
        assert results[0].verified_savings_kgco2e > 0


class TestEvidenceChain:
    """Tests for evidence chain integrity."""

    def test_hash_deterministic(self):
        """Same inputs must produce the same hash every time."""
        kwargs = dict(
            job_id="test-job",
            original_region="us-east-1",
            original_time=datetime(2025, 1, 15, 12),
            executed_region="eu-north-1",
            executed_time=datetime(2025, 1, 15, 12),
            vcpus=4, gpu_count=0, duration_hours=1.0,
        )
        h1 = _hash_inputs(**kwargs)
        h2 = _hash_inputs(**kwargs)
        assert h1 == h2, "Hash should be deterministic"
        assert len(h1) == 16, "Hash should be 16-char truncated SHA-256"

    def test_hash_changes_with_input(self):
        """Different inputs must produce different hashes."""
        base = dict(
            job_id="test-job",
            original_region="us-east-1",
            original_time=datetime(2025, 1, 15, 12),
            executed_region="eu-north-1",
            executed_time=datetime(2025, 1, 15, 12),
            vcpus=4, gpu_count=0, duration_hours=1.0,
        )
        modified = {**base, "executed_region": "us-west-2"}
        assert _hash_inputs(**base) != _hash_inputs(**modified)


class TestSummarizeVerification:
    """Tests for summarize_verification aggregation."""

    def test_empty_returns_zero_count(self):
        assert summarize_verification([])["count"] == 0

    def test_aggregates_correctly(self):
        idf = _make_intensity_df()
        original = _make_job(region="us-east-1")
        executed = _make_job(region="eu-north-1")
        rec = _make_recommendation()

        v = verify_single(rec, original, executed, idf)
        summary = summarize_verification([v])

        assert summary["count"] == 1
        assert summary["total_verified_savings_kgco2e"] > 0
        assert summary["sla_violations"] == 0
        assert summary["calibration_self_consistency"] == 100.0
