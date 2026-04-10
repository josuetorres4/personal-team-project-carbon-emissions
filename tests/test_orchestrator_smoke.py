"""
Smoke test for the full orchestrator pipeline.

Runs the complete Sense -> Model -> Decide -> Act -> Verify -> Learn loop
with mock LLM and 1 day of simulated data. Catches import breakage,
interface mismatches, and runtime errors across all agents.
"""

import os
import pytest

from src.orchestrator import Orchestrator


class TestOrchestratorSmoke:
    """End-to-end smoke test — pipeline must complete without exceptions."""

    @pytest.fixture(autouse=True)
    def setup_data_dir(self, tmp_path, monkeypatch):
        """Run pipeline in a temp directory so tests don't pollute data/."""
        monkeypatch.chdir(tmp_path)

    def test_full_pipeline_completes(self):
        """Pipeline runs end-to-end with mock LLM and returns valid summary."""
        orch = Orchestrator(llm_provider="mock", verbose=False)
        summary = orch.run(sim_days=1, seed=42)

        # Basic structure checks
        assert isinstance(summary, dict)
        assert summary["total_jobs"] > 0
        assert summary["simulation_days"] == 1
        assert summary["llm_provider"] == "mock"

        # Emissions should be non-negative
        assert summary["baseline"]["total_emissions_kgco2e"] >= 0
        assert summary["optimized"]["total_emissions_kgco2e"] >= 0
        assert summary["improvement"]["emissions_reduction_kgco2e"] >= 0

        # Pipeline stats
        assert summary["pipeline"]["recommendations_generated"] >= 0
        assert summary["pipeline"]["verifications_completed"] >= 0

    def test_output_files_written(self):
        """All expected CSV and JSON files should be written."""
        orch = Orchestrator(llm_provider="mock", verbose=False)
        orch.run(sim_days=1, seed=42)

        expected_files = [
            "data/jobs_baseline.csv",
            "data/jobs_optimized.csv",
            "data/carbon_intensity.csv",
            "data/recommendations.csv",
            "data/governance_decisions.csv",
            "data/executions.csv",
            "data/verifications.csv",
            "data/points.csv",
            "data/leaderboard.csv",
            "data/pipeline_summary.json",
            "data/evidence_chains.json",
            "data/agent_traces.json",
            "data/agent_dialogues.json",
        ]
        for f in expected_files:
            assert os.path.exists(f), f"Missing output file: {f}"
