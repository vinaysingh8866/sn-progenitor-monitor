from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime

import pytest

from sn_progenitor_monitor import monitor
from sn_progenitor_monitor.monitor import DataDir, desktop_notify, load_state, resolve_data_dir, run
from tests.conftest import NOW

COV = {
    "jwst": [
        {
            "obs_id": "jw01234",
            "instrument": "NIRCam",
            "filter": "F200W",
            "t_min_mjd": 60500.0,
            "t_exptime": 1200.0,
            "obs_date": "2024-07-14",
        }
    ],
    "hst": [],
}
NO_COV = {"jwst": [], "hst": []}


@pytest.fixture
def archives(monkeypatch):
    """Patch the archive lookups; returns a dict the test can tweak and a call log."""
    cfg = {"dist": {"NGC 1234": 20.0, "NGC 4321": 25.0}, "cov": {"SN 2026abc": COV, "SN 2026xyz": NO_COV}}
    calls = {"dist": [], "cov": [], "notify": []}

    def fake_dist(host):
        calls["dist"].append(host)
        return cfg["dist"].get(host)

    def fake_cov(ra, dec, sn_mjd):
        calls["cov"].append((ra, dec, sn_mjd))
        # look up by position: SN 2026abc is at RA 52.5
        name = "SN 2026abc" if abs(ra - 52.5) < 1e-6 else "SN 2026xyz"
        return cfg["cov"][name]

    monkeypatch.setattr(monitor, "host_distance_mpc", fake_dist)
    monkeypatch.setattr(monitor, "query_pre_explosion", fake_cov)
    monkeypatch.setattr(monitor, "desktop_notify", lambda *a, **k: calls["notify"].append(a) or True)
    return cfg, calls


def test_first_run_logs_hit_and_writes_everything(data_dir, candidates, archives, no_network):
    cfg, calls = archives
    res = run(data_dir, now=NOW, candidates=candidates)

    assert [h.sn.name for h in res.new_hits] == ["SN 2026abc"]
    assert [sn.name for sn in res.nearby_no_cov] == ["SN 2026xyz"]
    assert calls["dist"] == ["NGC 1234", "NGC 4321"]
    assert calls["cov"][0][:2] == (52.5, -12.25)

    d = DataDir(data_dir)
    assert d.state.exists() and d.report.exists() and d.last_run.exists()
    assert (d.hit_files / "HIT_SN 2026abc_20261008.txt").exists()
    assert "NEW HITS" in d.report.read_text()
    assert "jw01234" in d.report.read_text()
    assert len(calls["notify"]) == 1
    assert "NEW HIT" in calls["notify"][0][0]


def test_hits_jsonl_append_format(data_dir, candidates, archives, no_network):
    run(data_dir, now=NOW, candidates=candidates)
    lines = DataDir(data_dir).hits.read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["logged_at"] == NOW.isoformat()
    assert rec["sn"]["name"] == "SN 2026abc"
    assert rec["sn"]["discovered"] == "2026-09-30T00:00:00"
    assert rec["dist_mpc"] == 20.0
    assert rec["coverage"] == COV


def test_state_dedup_prevents_realert(data_dir, candidates, archives, no_network):
    cfg, calls = archives
    run(data_dir, now=NOW, candidates=candidates)
    res2 = run(data_dir, now=NOW, candidates=candidates)

    assert res2.new_hits == []
    assert "No new hits" in res2.report
    assert len(DataDir(data_dir).hits.read_text().splitlines()) == 1
    # distance is cached in state: NED not called again
    assert calls["dist"] == ["NGC 1234", "NGC 4321"]
    # coverage is re-checked every run
    assert len(calls["cov"]) == 4
    state = load_state(DataDir(data_dir).state)
    assert state["seen"]["SN 2026abc"]["alerted_n_jwst"] == 1
    assert state["last_run"] == NOW.isoformat()


def test_new_coverage_triggers_fresh_alert(data_dir, candidates, archives, no_network):
    cfg, calls = archives
    run(data_dir, now=NOW, candidates=candidates)
    cfg["cov"]["SN 2026abc"] = {"jwst": COV["jwst"], "hst": [dict(COV["jwst"][0], obs_id="hst9")]}
    res = run(data_dir, now=NOW, candidates=candidates)
    assert [h.sn.name for h in res.new_hits] == ["SN 2026abc"]
    assert len(DataDir(data_dir).hits.read_text().splitlines()) == 2


def test_far_and_unknown_hosts_skip_mast(data_dir, candidates, archives, no_network):
    cfg, calls = archives
    cfg["dist"] = {"NGC 1234": 80.0}  # NGC 4321 unresolvable
    res = run(data_dir, now=NOW, candidates=candidates)
    assert [sn.name for sn in res.far_skipped] == ["SN 2026abc"]
    assert [sn.name for sn in res.unknown_dist] == ["SN 2026xyz"]
    assert calls["cov"] == []
    assert res.new_hits == []


def test_dry_run_writes_nothing_and_does_not_notify(data_dir, candidates, archives, no_network):
    cfg, calls = archives
    res = run(data_dir, now=NOW, candidates=candidates, dry_run=True)
    assert [h.sn.name for h in res.new_hits] == ["SN 2026abc"]
    assert not data_dir.exists()
    assert calls["notify"] == []
    # and a following real run still treats it as new
    res2 = run(data_dir, now=NOW, candidates=candidates)
    assert len(res2.new_hits) == 1


def test_notification_skipped_when_osascript_missing(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(a))
    assert desktop_notify("t", "m") is False
    assert calls == []


def test_notification_calls_osascript_when_present(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/osascript")
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: calls.append(cmd))
    assert desktop_notify('say "hi"', "msg", sound=True) is True
    assert calls[0][0] == "osascript"
    assert 'display notification "msg" with title "say \\"hi\\"" sound name "Glass"' == calls[0][2]


def test_resolve_data_dir_order(monkeypatch, tmp_path):
    monkeypatch.delenv("SN_MONITOR_DIR", raising=False)
    assert resolve_data_dir() == monitor.Path("~/.sn-progenitor-monitor").expanduser()
    monkeypatch.setenv("SN_MONITOR_DIR", str(tmp_path / "env"))
    assert resolve_data_dir() == tmp_path / "env"
    assert resolve_data_dir(tmp_path / "flag") == tmp_path / "flag"


def test_load_state_tolerates_corrupt_file(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("{not json")
    assert load_state(p) == {"seen": {}}


def test_report_lists_nearby_without_coverage(data_dir, candidates, archives, no_network):
    cfg, calls = archives
    cfg["cov"] = {"SN 2026abc": NO_COV, "SN 2026xyz": NO_COV}
    res = run(data_dir, now=datetime(2026, 10, 8), candidates=candidates)
    assert "Nearby SNe under monitoring" in res.report
    assert "SN 2026abc" in res.report and "D=20.0 Mpc" in res.report
    assert "under watch" in calls["notify"][0][0]
