"""Tests for business logic functions (allocate_memory, start/stop, state)."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import main  # noqa: E402
from main import (  # noqa: E402
    allocate_memory,
    STATE,
    start_job,
    stop_job,
    status_payload,
    _set_state_running,
    _set_state_stopped,
)


# ── allocate_memory ────────────────────────────────────────────────────────

class TestAllocateMemory:
    def test_allocates_requested_amount(self):
        allocate_memory(10)  # 10 MiB
        total_bytes = sum(len(b) for b in main._mem_blocks)
        assert total_bytes == 10 * 1024 * 1024

    def test_allocates_small_amount(self):
        allocate_memory(1)
        total_bytes = sum(len(b) for b in main._mem_blocks)
        assert total_bytes == 1 * 1024 * 1024

    def test_allocates_zero_produces_empty(self):
        allocate_memory(0)
        assert len(main._mem_blocks) == 0


# ── _set_state_running / _set_state_stopped ────────────────────────────────

class TestStateHelpers:
    def test_set_state_running(self):
        # Use a mock-like object with pid attribute
        class FakeProc:
            pid = 12345

        _set_state_running(512, 2, 60, [FakeProc(), FakeProc()])
        assert STATE["running"] is True
        assert STATE["mem_mib"] == 512
        assert STATE["cpu_workers"] == 2
        assert STATE["pid_workers"] == [12345, 12345]
        assert STATE["started_at"] is not None
        assert STATE["ends_at"] > STATE["started_at"]

    def test_set_state_stopped(self):
        _set_state_stopped("motivo teste")
        assert STATE["running"] is False
        assert STATE["note"] == "motivo teste"
        assert STATE["ends_at"] is not None

    def test_set_state_stopped_default_note(self):
        _set_state_stopped()
        assert STATE["note"] == ""


# ── stop_job ───────────────────────────────────────────────────────────────

class TestStopJob:
    def test_stop_when_already_stopped(self):
        stop_job("teste")
        assert STATE["running"] is False
        assert STATE["note"] == "Já estava parado."

    def test_stop_after_start(self):
        start_job(64, 1, 30)
        assert STATE["running"] is True
        stop_job("teste stop")
        assert STATE["running"] is False
        assert STATE["note"] == "teste stop"


# ── start_job ──────────────────────────────────────────────────────────────

class TestStartJob:
    def test_start_returns_iniciado(self):
        result = start_job(64, 1, 10)
        assert result == "Iniciado"

    def test_start_sets_running(self):
        start_job(64, 1, 10)
        assert STATE["running"] is True
        assert STATE["mem_mib"] == 64
        assert STATE["cpu_workers"] == 1

    def test_double_start_returns_already_running(self):
        start_job(64, 1, 10)
        result = start_job(64, 1, 10)
        assert "rodando" in result.lower()

    def test_start_creates_pid_workers(self):
        start_job(64, 2, 10)
        assert len(STATE["pid_workers"]) == 2
        for pid in STATE["pid_workers"]:
            assert isinstance(pid, int)
            assert pid > 0


# ── status_payload ─────────────────────────────────────────────────────────

class TestStatusPayload:
    def test_payload_when_stopped(self):
        payload = status_payload()
        assert payload["running"] is False
        assert payload["remaining_seconds"] is None
        assert "now" in payload
        assert "mem_blocks_mib" in payload

    def test_payload_when_running(self):
        start_job(64, 1, 30)
        payload = status_payload()
        assert payload["running"] is True
        assert payload["remaining_seconds"] is not None
        assert payload["remaining_seconds"] <= 30
        assert payload["remaining_seconds"] >= 0

    def test_payload_includes_mem_blocks_count(self):
        allocate_memory(5)
        payload = status_payload()
        assert payload["mem_blocks_mib"] == len(main._mem_blocks)
