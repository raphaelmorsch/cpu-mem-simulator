"""Tests for the FastAPI HTTP endpoints."""

import json
import time


# ── GET / ──────────────────────────────────────────────────────────────────

class TestIndexPage:
    def test_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_contains_title(self, client):
        resp = client.get("/")
        assert "CPU/RAM Simulator" in resp.text


# ── GET /api/status ────────────────────────────────────────────────────────

class TestApiStatus:
    def test_returns_json(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"

    def test_default_state_is_stopped(self, client):
        data = client.get("/api/status").json()
        assert data["running"] is False
        assert data["mem_mib"] == 0
        assert data["cpu_workers"] == 0
        assert data["ticks"] == 0

    def test_status_has_expected_keys(self, client):
        data = client.get("/api/status").json()
        expected_keys = {
            "running", "started_at", "ends_at", "mem_mib",
            "cpu_workers", "pid_workers", "note", "ticks",
            "now", "remaining_seconds", "mem_blocks_mib",
        }
        assert expected_keys.issubset(data.keys())


# ── POST /api/start ───────────────────────────────────────────────────────

class TestApiStart:
    def test_start_returns_200(self, client):
        payload = {"mem_mib": 64, "cpu_workers": 1, "seconds": 5}
        resp = client.post("/api/start", json=payload)
        assert resp.status_code == 200
        assert "Iniciado" in resp.text

    def test_start_changes_state_to_running(self, client):
        client.post("/api/start", json={"mem_mib": 64, "cpu_workers": 1, "seconds": 10})
        data = client.get("/api/status").json()
        assert data["running"] is True
        assert data["cpu_workers"] == 1
        assert data["mem_mib"] == 64

    def test_start_while_running_returns_already_running(self, client):
        client.post("/api/start", json={"mem_mib": 64, "cpu_workers": 1, "seconds": 10})
        resp = client.post("/api/start", json={"mem_mib": 64, "cpu_workers": 1, "seconds": 10})
        assert "rodando" in resp.text.lower()

    def test_start_uses_defaults_when_no_payload(self, client):
        resp = client.post("/api/start", json={})
        assert resp.status_code == 200
        data = client.get("/api/status").json()
        assert data["running"] is True
        # defaults: mem_mib=1900, cpu_workers=2, seconds=120
        assert data["mem_mib"] == 1900
        assert data["cpu_workers"] == 2


# ── POST /api/stop ────────────────────────────────────────────────────────

class TestApiStop:
    def test_stop_returns_200(self, client):
        resp = client.post("/api/stop")
        assert resp.status_code == 200

    def test_stop_when_not_running(self, client):
        resp = client.post("/api/stop")
        assert resp.status_code == 200
        assert "Parado" in resp.text

    def test_stop_after_start(self, client):
        client.post("/api/start", json={"mem_mib": 64, "cpu_workers": 1, "seconds": 30})
        data = client.get("/api/status").json()
        assert data["running"] is True

        resp = client.post("/api/stop")
        assert resp.status_code == 200

        data = client.get("/api/status").json()
        assert data["running"] is False


# ── Guardrails ─────────────────────────────────────────────────────────────

class TestGuardrails:
    def test_mem_mib_clamped_to_min(self, client):
        client.post("/api/start", json={"mem_mib": 1, "cpu_workers": 1, "seconds": 5})
        data = client.get("/api/status").json()
        assert data["mem_mib"] >= 64

    def test_mem_mib_clamped_to_max(self, client):
        client.post("/api/start", json={"mem_mib": 99999, "cpu_workers": 1, "seconds": 5})
        data = client.get("/api/status").json()
        assert data["mem_mib"] <= 3000

    def test_cpu_workers_clamped_to_min(self, client):
        client.post("/api/start", json={"mem_mib": 64, "cpu_workers": 0, "seconds": 5})
        data = client.get("/api/status").json()
        assert data["cpu_workers"] >= 1

    def test_cpu_workers_clamped_to_max(self, client):
        client.post("/api/start", json={"mem_mib": 64, "cpu_workers": 100, "seconds": 5})
        data = client.get("/api/status").json()
        assert data["cpu_workers"] <= 32

    def test_seconds_clamped_to_min(self, client):
        client.post("/api/start", json={"mem_mib": 64, "cpu_workers": 1, "seconds": 1})
        data = client.get("/api/status").json()
        # Validate via ends_at - started_at (immune to race conditions)
        duration = data["ends_at"] - data["started_at"]
        assert duration >= 5  # clamped from 1 to min=5

    def test_seconds_clamped_to_max(self, client):
        client.post("/api/start", json={"mem_mib": 64, "cpu_workers": 1, "seconds": 99999})
        data = client.get("/api/status").json()
        duration = data["ends_at"] - data["started_at"]
        assert duration <= 3600  # clamped to max=3600


# ── WebSocket ──────────────────────────────────────────────────────────────

class TestWebSocket:
    def test_ws_connects_and_receives_status(self, client):
        with client.websocket_connect("/ws") as ws:
            msg = ws.receive_text()
            data = json.loads(msg)
            assert "running" in data
            assert "now" in data

    def test_ws_reflects_running_state(self, client):
        client.post("/api/start", json={"mem_mib": 64, "cpu_workers": 1, "seconds": 30})
        with client.websocket_connect("/ws") as ws:
            msg = ws.receive_text()
            data = json.loads(msg)
            assert data["running"] is True
