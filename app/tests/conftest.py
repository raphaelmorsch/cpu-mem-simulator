"""Shared fixtures for cpu-mem-simulator tests."""

import sys
import os
import time
import pytest
from fastapi.testclient import TestClient

# Ensure app directory is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app, STATE, stop_job, _mem_blocks  # noqa: E402


@pytest.fixture(autouse=True)
def reset_state():
    """Reset global state before every test to ensure isolation."""
    stop_job("test cleanup")
    # Wait briefly for processes to terminate
    time.sleep(0.1)
    STATE.update({
        "running": False,
        "started_at": None,
        "ends_at": None,
        "mem_mib": 0,
        "cpu_workers": 0,
        "pid_workers": [],
        "note": "",
        "ticks": 0,
    })
    yield
    # Cleanup after test
    stop_job("test cleanup")
    time.sleep(0.1)


@pytest.fixture
def client():
    """FastAPI TestClient instance."""
    return TestClient(app)
