"""
Tests for src/shared/proof_of_impact.py

Covers ProofOfImpactCard to_dict, verdict generation, and PDF output.
"""

import pytest
from src.shared.proof_of_impact import ProofOfImpactCard


def _make_verification(saving_kg=10.0, significant=True, real=False):
    return {
        "point_estimate_kg": saving_kg,
        "ci_lower_kg": 2.0 if significant else -1.0,
        "ci_upper_kg": 18.0,
        "saving_is_significant": significant,
        "action": "region_shift",
        "counterfactual_kg": saving_kg * 2,
        "actual_kg": saving_kg,
        "method": "bootstrap",
        "carbon_data_source": "simulated",
        "is_real": real,
    }


def _make_job(job_id="job-001", team="team-alpha"):
    return {"job_id": job_id, "team": team}


def _make_market():
    return {"week": "2026-W10", "budgets": {}, "trades": [], "market_summary": {}}


class TestProofOfImpactCard:
    def test_to_dict_structure(self):
        card = ProofOfImpactCard(
            verification=_make_verification(),
            job=_make_job(),
            market=_make_market(),
        )
        d = card.to_dict()
        assert d["evidence_id"] == "POI-job-001"
        assert d["job_id"] == "job-001"
        assert d["team"] == "team-alpha"
        assert d["carbon_saving_kg"] == 10.0
        assert d["saving_is_significant"] is True
        assert d["csrd_scope"] == "Scope 2 - cloud compute"
        assert d["ghg_protocol_method"] == "Location-based"

    def test_to_dict_carbon_saving_tonnes(self):
        card = ProofOfImpactCard(
            verification=_make_verification(saving_kg=1000.0),
            job=_make_job(),
            market=_make_market(),
        )
        d = card.to_dict()
        assert d["carbon_saving_tonnes"] == 1.0

    def test_verdict_significant(self):
        card = ProofOfImpactCard(
            verification=_make_verification(saving_kg=50.0, significant=True),
            job=_make_job(),
            market=_make_market(),
        )
        d = card.to_dict()
        assert "Verified saving" in d["plain_english_verdict"]
        assert "CSRD Scope 2" in d["plain_english_verdict"]

    def test_verdict_strong_saving(self):
        card = ProofOfImpactCard(
            verification=_make_verification(saving_kg=150.0, significant=True),
            job=_make_job(),
            market=_make_market(),
        )
        d = card.to_dict()
        assert "Strong verified saving" in d["plain_english_verdict"]

    def test_verdict_not_significant(self):
        card = ProofOfImpactCard(
            verification=_make_verification(significant=False),
            job=_make_job(),
            market=_make_market(),
        )
        d = card.to_dict()
        assert "not statistically significant" in d["plain_english_verdict"]

    def test_counterfactual_description(self):
        card = ProofOfImpactCard(
            verification=_make_verification(saving_kg=10.0),
            job=_make_job(),
            market=_make_market(),
        )
        d = card.to_dict()
        assert "20.000 kg CO2e" in d["counterfactual_description"]
        assert "10.000 kg CO2e" in d["counterfactual_description"]

    def test_is_real_data_flag(self):
        card = ProofOfImpactCard(
            verification=_make_verification(real=True),
            job=_make_job(),
            market=_make_market(),
        )
        d = card.to_dict()
        assert d["is_real_data"] is True

    def test_to_pdf_creates_file(self, tmp_path):
        card = ProofOfImpactCard(
            verification=_make_verification(),
            job=_make_job(),
            market=_make_market(),
        )
        pdf_path = str(tmp_path / "test_evidence.pdf")
        card.to_pdf(pdf_path)
        import os
        assert os.path.exists(pdf_path)
        assert os.path.getsize(pdf_path) > 0

    def test_to_pdf_handles_none_values(self, tmp_path):
        v = _make_verification()
        v["ci_lower_kg"] = None
        v["ci_upper_kg"] = None
        v["point_estimate_kg"] = None
        card = ProofOfImpactCard(
            verification=v,
            job=_make_job(),
            market=_make_market(),
        )
        pdf_path = str(tmp_path / "test_none.pdf")
        card.to_pdf(pdf_path)
        import os
        assert os.path.exists(pdf_path)
