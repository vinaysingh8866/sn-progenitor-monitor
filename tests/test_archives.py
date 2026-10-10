from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from sn_progenitor_monitor.archives import host_distance_mpc, mjd, mjd_to_date, query_pre_explosion

pytest.importorskip("astroquery")


def test_mjd_roundtrip():
    assert mjd(datetime(1858, 11, 17)) == 0.0
    assert mjd(datetime(2000, 1, 1)) == pytest.approx(51544.0)
    assert mjd_to_date(51544.0) == "2000-01-01"


def test_host_distance_from_ned_redshift():
    with patch("astroquery.ipac.ned.Ned.query_object", return_value=[{"Redshift": 0.005}]) as q:
        d = host_distance_mpc("NGC 1234")
    q.assert_called_once_with("NGC 1234")
    assert d == pytest.approx(0.005 * 3e5 / 70.0)


@pytest.mark.parametrize("table", [[], [{"Redshift": None}], [{"Redshift": -0.001}], [{"Redshift": 0.9}]])
def test_host_distance_unresolvable(table):
    with patch("astroquery.ipac.ned.Ned.query_object", return_value=table):
        assert host_distance_mpc("NGC 1234") is None


def test_host_distance_skips_empty_host():
    with patch("astroquery.ipac.ned.Ned.query_object") as q:
        assert host_distance_mpc("") is None
        assert host_distance_mpc("none") is None
    q.assert_not_called()


def test_host_distance_swallows_query_errors():
    with patch("astroquery.ipac.ned.Ned.query_object", side_effect=RuntimeError("NED down")):
        assert host_distance_mpc("NGC 1234") is None


def _obs(coll, obs_id, t_min, inst="NIRCam", filt="F200W", exp=1000.0):
    return {
        "obs_collection": coll,
        "obs_id": obs_id,
        "t_min": t_min,
        "instrument_name": inst,
        "filters": filt,
        "t_exptime": exp,
    }


def test_query_pre_explosion_coordinates_and_filtering():
    sn_mjd = 61000.0
    rows = [
        _obs("JWST", "jw1", 60500.0),
        _obs("HST", "hst1", 55000.0, inst="WFC3/UVIS", filt="F555W"),
        _obs("JWST", "jw2", 61500.0),  # after explosion -> dropped
        _obs("HST", "hst2", None),  # no start time -> dropped
        _obs("TESS", "tess1", 60000.0),  # other collection -> dropped
    ]
    with patch("astroquery.mast.Observations.query_criteria", return_value=rows) as q:
        cov = query_pre_explosion(52.5, -12.25, sn_mjd)

    q.assert_called_once()
    kw = q.call_args.kwargs
    assert kw["coordinates"].ra.deg == pytest.approx(52.5)
    assert kw["coordinates"].dec.deg == pytest.approx(-12.25)
    assert kw["radius"].to_value("arcmin") == pytest.approx(1.5)
    assert kw["obs_collection"] == ["JWST", "HST"]
    assert kw["dataproduct_type"] == "image"

    assert [o["obs_id"] for o in cov["jwst"]] == ["jw1"]
    assert [o["obs_id"] for o in cov["hst"]] == ["hst1"]
    assert cov["jwst"][0]["obs_date"] == mjd_to_date(60500.0)
    assert cov["hst"][0]["instrument"] == "WFC3/UVIS"
    assert "error" not in cov


def test_query_pre_explosion_reports_errors():
    with patch("astroquery.mast.Observations.query_criteria", side_effect=RuntimeError("MAST timeout")):
        cov = query_pre_explosion(10.0, 20.0, 61000.0)
    assert cov == {"error": "MAST timeout", "jwst": [], "hst": []}
