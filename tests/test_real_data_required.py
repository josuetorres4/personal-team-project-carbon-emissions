"""Pre-flight test: REAL_DATA_ONLY mode must abort the orchestrator before any agent runs."""

import os
from unittest.mock import patch

import pytest


def _reload(env: dict):
    import importlib
    with patch.dict(os.environ, env, clear=False):
        import config
        importlib.reload(config)
        from src import orchestrator
        importlib.reload(orchestrator)
        return orchestrator


def test_preflight_aborts_when_carbon_keys_missing():
    """Preflight must raise when REAL_DATA_ONLY is on but no carbon API key is configured."""
    orchestrator = _reload({
        "REAL_DATA_ONLY": "true",
        "USE_REAL_CARBON_DATA": "true",
        "USE_REAL_WORKLOAD_DATA": "true",
        "ELECTRICITYMAPS_API_TOKEN": "",
        "EIA_API_KEY": "",
        "ENTSOE_API_TOKEN": "",
        "WORKLOAD_DATA_PATH": "data/azure_traces/vmtable.csv",
    })

    with pytest.raises(RuntimeError, match="REAL_DATA_ONLY"):
        orchestrator.Orchestrator.preflight_real_data_check()


def test_preflight_aborts_when_workload_csv_missing():
    """Preflight must raise when REAL_DATA_ONLY is on but the Azure CSV is absent."""
    orchestrator = _reload({
        "REAL_DATA_ONLY": "true",
        "USE_REAL_CARBON_DATA": "true",
        "USE_REAL_WORKLOAD_DATA": "true",
        "ELECTRICITYMAPS_API_TOKEN": "fake-token",
        "WORKLOAD_DATA_PATH": "/nonexistent/path/vmtable.csv",
    })

    with pytest.raises(RuntimeError, match="workload CSV"):
        orchestrator.Orchestrator.preflight_real_data_check()


def test_preflight_passes_when_legacy_mode():
    """Preflight is a no-op in legacy mode."""
    orchestrator = _reload({
        "REAL_DATA_ONLY": "false",
    })
    orchestrator.Orchestrator.preflight_real_data_check()  # must not raise
