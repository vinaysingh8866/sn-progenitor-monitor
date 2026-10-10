from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from sn_progenitor_monitor.scrape import filter_candidates, parse_rows

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 8, 12, 0, 0)


@pytest.fixture(scope="session")
def sample_html() -> str:
    return (FIXTURES / "snlocations_sample.html").read_text()


@pytest.fixture(scope="session")
def parsed(sample_html):
    return parse_rows(sample_html)


@pytest.fixture(scope="session")
def candidates(parsed):
    return filter_candidates(parsed, now=NOW)


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path, monkeypatch):
    """Never let a test touch the real ~/.sn-progenitor-monitor."""
    monkeypatch.setenv("SN_MONITOR_DIR", str(tmp_path / "default-data"))


@pytest.fixture
def data_dir(tmp_path, monkeypatch) -> Path:
    d = tmp_path / "data"
    monkeypatch.setenv("SN_MONITOR_DIR", str(d))
    return d


@pytest.fixture
def no_network(monkeypatch):
    """Fail loudly if anything tries to use requests."""
    import requests

    def boom(*a, **k):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(requests, "get", boom)
