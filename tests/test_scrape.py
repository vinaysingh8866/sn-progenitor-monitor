from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from sn_progenitor_monitor import scrape
from sn_progenitor_monitor.scrape import BISHOP_URL, Supernova, fetch_sne, filter_candidates, parse_rows
from tests.conftest import NOW


def test_parse_returns_well_formed_rows_only(parsed):
    # 7 rows in the fixture; the one with date 2026/02/30 has an invalid day and is dropped
    assert [sn.name for sn in parsed] == [
        "SN 2026abc",
        "SN 2026xyz",
        "SN 2026ia1",
        "SN 2026old",
        "SN 2026fnt",
        "SN 2026sls",
    ]


def test_parse_fields(parsed):
    sn = parsed[0]
    assert isinstance(sn, Supernova)
    assert sn.name == "SN 2026abc"
    assert sn.type == "II"
    assert sn.date == "2026/09/30.512"
    assert sn.discovered == datetime(2026, 9, 30)
    assert sn.mag == pytest.approx(16.8)
    assert sn.ra == pytest.approx(3.5 * 15.0)  # hours -> degrees
    assert sn.dec == pytest.approx(-12.25)
    assert sn.host == "NGC 1234"
    assert sn.survey_id == "ZTF26abcd"


def test_parse_handles_td_attributes_and_anchor_attributes(parsed):
    sn = parsed[1]
    assert sn.name == "SN 2026xyz"
    assert sn.ra == pytest.approx(12.123 * 15.0)
    assert sn.dec == pytest.approx(45.5)


def test_parse_empty_html():
    assert parse_rows("<html></html>") == []


def test_filter_keeps_exactly_the_two_valid_core_collapse(candidates):
    assert {sn.name for sn in candidates} == {"SN 2026abc", "SN 2026xyz"}


def test_filter_sorted_brightest_first(candidates):
    assert [sn.name for sn in candidates] == ["SN 2026abc", "SN 2026xyz"]
    assert candidates[0].mag < candidates[1].mag


@pytest.mark.parametrize(
    "name,reason",
    [("SN 2026ia1", "Type Ia"), ("SN 2026old", "outside lookback"), ("SN 2026fnt", "fainter than MAG_MAX")],
)
def test_filter_excludes(candidates, name, reason):
    assert name not in {sn.name for sn in candidates}, reason


def test_filter_window_is_relative_to_now(parsed):
    # Move "now" back to May 2026: the old SN is now inside the window, the September ones are in the future.
    kept = filter_candidates(parsed, now=datetime(2026, 5, 10))
    assert {sn.name for sn in kept} == {"SN 2026old", "SN 2026abc", "SN 2026xyz"}
    kept = filter_candidates(parsed, now=NOW, lookback_days=30)
    assert {sn.name for sn in kept} == {"SN 2026abc"}


def test_filter_mag_cut_override(parsed):
    kept = filter_candidates(parsed, now=NOW, mag_max=20.0)
    assert "SN 2026fnt" in {sn.name for sn in kept}


def test_supernova_roundtrip(parsed):
    sn = parsed[0]
    d = sn.to_dict()
    assert d["discovered"] == "2026-09-30T00:00:00"
    assert Supernova.from_dict(d) == sn


def test_fetch_sne_uses_requests(sample_html):
    resp = MagicMock()
    resp.text = sample_html
    with patch.object(scrape.requests, "get", return_value=resp) as get:
        sne = fetch_sne(now=NOW)
    get.assert_called_once_with(BISHOP_URL, timeout=scrape.HTTP_TIMEOUT)
    resp.raise_for_status.assert_called_once()
    assert len(sne) == 2
