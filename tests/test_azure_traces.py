"""Tests for Azure VM traces workload data loader."""

import os
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest


def _reload_config_with(env: dict):
    import importlib
    with patch.dict(os.environ, env, clear=False):
        import config
        importlib.reload(config)
        return config


def test_real_data_only_raises_when_workload_csv_missing():
    """REAL_DATA_ONLY=true with missing CSV must raise FileNotFoundError."""
    _reload_config_with({
        "REAL_DATA_ONLY": "true",
        "USE_REAL_WORKLOAD_DATA": "true",
        "WORKLOAD_DATA_PATH": "/nonexistent/path/vmtable.csv",
    })
    import importlib
    from src.data import azure_traces
    importlib.reload(azure_traces)

    with pytest.raises(FileNotFoundError):
        azure_traces.get_workload_data(datetime(2025, 1, 1), sim_days=1, seed=42)


def test_real_data_only_requires_workload_flag():
    """REAL_DATA_ONLY=true with USE_REAL_WORKLOAD_DATA=false must raise."""
    _reload_config_with({
        "REAL_DATA_ONLY": "true",
        "USE_REAL_WORKLOAD_DATA": "false",
    })
    import importlib
    from src.data import azure_traces
    importlib.reload(azure_traces)

    with pytest.raises(RuntimeError, match="USE_REAL_WORKLOAD_DATA=true"):
        azure_traces.get_workload_data(datetime(2025, 1, 1), sim_days=1, seed=42)


def test_legacy_mode_falls_back_to_synthetic():
    """REAL_DATA_ONLY=false must still allow synthetic generation."""
    _reload_config_with({
        "REAL_DATA_ONLY": "false",
        "USE_REAL_WORKLOAD_DATA": "false",
    })
    import importlib
    from src.data import azure_traces
    importlib.reload(azure_traces)

    jobs = azure_traces.get_workload_data(datetime(2025, 1, 1), sim_days=1, seed=42)
    assert len(jobs) > 0
    assert not any(j.job_id.startswith("az-") for j in jobs)


def test_vm_category_to_sla_mapping():
    """vmCategory should map correctly to WorkloadCategory."""
    from src.data.azure_traces import _map_vm_category_to_sla
    from src.shared.models import WorkloadCategory

    assert _map_vm_category_to_sla("Delay-insensitive") == WorkloadCategory.SUSTAINABLE
    assert _map_vm_category_to_sla("Interactive") == WorkloadCategory.URGENT
    assert _map_vm_category_to_sla("Unknown") == WorkloadCategory.BALANCED
    assert _map_vm_category_to_sla("") == WorkloadCategory.BALANCED
    assert _map_vm_category_to_sla(None) == WorkloadCategory.BALANCED


def test_workload_type_mapping():
    """Workload type heuristics should produce valid types."""
    from src.data.azure_traces import _map_to_workload_type

    valid_types = {"ci_cd", "batch_analytics", "model_training", "dev_test", "production"}

    assert _map_to_workload_type("Interactive", 6.0, 32, True) == "model_training"
    assert _map_to_workload_type("Interactive", 0.3, 4, False) == "ci_cd"
    assert _map_to_workload_type("Interactive", 24.0, 8, False) == "production"
    assert _map_to_workload_type("Delay-insensitive", 3.0, 16, False) == "batch_analytics"

    for cat in ["Interactive", "Delay-insensitive", "Unknown"]:
        for dur in [0.1, 1.0, 5.0, 24.0]:
            for cores in [2, 8, 32]:
                result = _map_to_workload_type(cat, dur, cores, False)
                assert result in valid_types, f"Invalid type {result} for {cat}/{dur}/{cores}"


def test_region_assignment_is_deterministic():
    """Same subscription_id should always map to the same region."""
    from src.data.azure_traces import _assign_region
    import numpy as np

    rng = np.random.default_rng(42)
    sub_id = "test-subscription-abc123"

    region1 = _assign_region(sub_id, rng)
    region2 = _assign_region(sub_id, rng)
    assert region1 == region2


def test_team_assignment_is_deterministic():
    """Same subscription_id should always map to the same team."""
    from src.data.azure_traces import _assign_team, TEAMS

    sub_id = "test-subscription-xyz789"
    team1 = _assign_team(sub_id)
    team2 = _assign_team(sub_id)

    assert team1 == team2
    assert team1 in TEAMS
