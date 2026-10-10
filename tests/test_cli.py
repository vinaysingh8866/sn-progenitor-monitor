from __future__ import annotations

import json

import pytest

from sn_progenitor_monitor import cli, monitor
from sn_progenitor_monitor.cli import _normalise_argv, main
from sn_progenitor_monitor.monitor import DataDir
from tests.test_monitor import COV, NO_COV


@pytest.fixture
def fake_pipeline(monkeypatch, candidates):
    notified = []
    monkeypatch.setattr(monitor, "fetch_sne", lambda now=None: candidates)
    monkeypatch.setattr(monitor, "host_distance_mpc", lambda host: 20.0)
    monkeypatch.setattr(monitor, "query_pre_explosion", lambda ra, dec, m: COV if abs(ra - 52.5) < 1e-6 else NO_COV)
    monkeypatch.setattr(monitor, "desktop_notify", lambda *a, **k: notified.append(a) or True)
    return notified


def test_run_is_default_subcommand():
    assert _normalise_argv([]) == ["run"]
    assert _normalise_argv(["--dry-run"]) == ["run", "--dry-run"]
    assert _normalise_argv(["report"]) == ["report"]
    assert _normalise_argv(["--help"]) == ["--help"]


def test_cli_dry_run_writes_nothing(tmp_path, fake_pipeline, capsys, no_network):
    d = tmp_path / "data"
    assert main(["--data-dir", str(d), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "NEW HITS" in out
    assert not d.exists()
    assert fake_pipeline == []


def test_cli_run_writes_state_and_notifies(tmp_path, fake_pipeline, capsys, no_network):
    d = tmp_path / "data"
    assert main(["--data-dir", str(d), "run", "--once"]) == 0
    assert DataDir(d).state.exists()
    assert len(fake_pipeline) == 1


def test_cli_json_prints_hits(tmp_path, fake_pipeline, capsys, no_network):
    d = tmp_path / "data"
    assert main(["run", "--data-dir", str(d), "--json", "--no-notify"]) == 0
    hits = json.loads(capsys.readouterr().out)
    assert [h["sn"]["name"] for h in hits] == ["SN 2026abc"]
    assert hits[0]["coverage"]["jwst"][0]["obs_id"] == "jw01234"
    assert fake_pipeline == []


def test_cli_data_dir_overrides_env(tmp_path, monkeypatch, fake_pipeline, no_network):
    env_dir = tmp_path / "from-env"
    flag_dir = tmp_path / "from-flag"
    monkeypatch.setenv("SN_MONITOR_DIR", str(env_dir))
    main(["--data-dir", str(flag_dir), "--no-notify"])
    assert flag_dir.exists() and not env_dir.exists()
    main(["--no-notify"])
    assert env_dir.exists()


def test_cli_report_prints_last_report(tmp_path, capsys):
    d = tmp_path / "data"
    assert main(["--data-dir", str(d), "report"]) == 1
    assert "no report yet" in capsys.readouterr().err
    DataDir(d).ensure()
    DataDir(d).report.write_text("hello report")
    assert main(["report", "--data-dir", str(d)]) == 0
    assert "hello report" in capsys.readouterr().out


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert "sn-monitor" in capsys.readouterr().out
