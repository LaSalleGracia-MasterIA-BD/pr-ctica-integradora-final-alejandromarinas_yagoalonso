"""End-to-end smoke test of the dashboard service.

Verifies that the dashboard's Streamlit health endpoint is up while the
stack is running. Skipped cleanly if the dashboard port is not reachable
(e.g. when only the pipeline/api services are up).
"""
from __future__ import annotations

import socket

import pytest


DASHBOARD_HOST_CANDIDATES = ("dashboard", "localhost", "127.0.0.1")
DASHBOARD_PORT = 8501


def _resolve_dashboard_url() -> str:
    for host in DASHBOARD_HOST_CANDIDATES:
        try:
            with socket.create_connection((host, DASHBOARD_PORT), timeout=1):
                return f"http://{host}:{DASHBOARD_PORT}"
        except OSError:
            continue
    pytest.skip(f"Dashboard not reachable on port {DASHBOARD_PORT}")


def test_dashboard_health_endpoint_returns_ok(http):
    url = _resolve_dashboard_url()
    response = http.get(f"{url}/_stcore/health")
    assert response.status_code == 200
    assert "ok" in response.text.lower()


def test_dashboard_root_returns_html(http):
    """Root path renders the Streamlit shell (HTML)."""
    url = _resolve_dashboard_url()
    response = http.get(f"{url}/")
    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("text/html")
