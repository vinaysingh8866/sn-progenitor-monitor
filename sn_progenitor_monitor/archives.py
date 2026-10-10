"""Archive lookups: NED host distance and MAST pre-explosion HST/JWST coverage.

astropy/astroquery are imported lazily so the scraper and CLI work without them.
"""

from __future__ import annotations

from datetime import datetime, timedelta

MJD_EPOCH = datetime(1858, 11, 17)
H0 = 70.0  # km/s/Mpc
C_KMS = 3e5
Z_MAX = 0.5

# ------------------------------ tunables ------------------------------
SEARCH_RADIUS_ARCMIN = 1.5  # MAST cone radius around the SN position


def mjd(dt: datetime) -> float:
    return (dt - MJD_EPOCH).total_seconds() / 86400.0


def mjd_to_date(value: float) -> str:
    return (MJD_EPOCH + timedelta(days=float(value))).strftime("%Y-%m-%d")


def host_distance_mpc(host: str) -> float | None:
    """Hubble-flow distance from the NED redshift of ``host``. None if not resolvable."""
    if not host or host == "none":
        return None
    try:
        from astroquery.ipac.ned import Ned

        t = Ned.query_object(host)
        if len(t) == 0:
            return None
        z = t[0]["Redshift"]
        if z is None or (hasattr(z, "mask") and z.mask):
            return None
        zf = float(z)
    except Exception:
        return None
    if zf <= 0 or zf > Z_MAX:
        return None
    return zf * C_KMS / H0


def query_pre_explosion(ra: float, dec: float, sn_mjd: float, radius_arcmin: float = SEARCH_RADIUS_ARCMIN) -> dict:
    """HST/JWST image observations at (ra, dec) that started before ``sn_mjd``.

    Returns ``{"jwst": [...], "hst": [...]}`` and an ``"error"`` key when the query failed.
    """
    import astropy.units as u
    from astropy.coordinates import SkyCoord
    from astroquery.mast import Observations

    coord = SkyCoord(ra=ra * u.deg, dec=dec * u.deg)
    try:
        obs = Observations.query_criteria(
            coordinates=coord,
            radius=radius_arcmin * u.arcmin,
            obs_collection=["JWST", "HST"],
            dataproduct_type="image",
        )
    except Exception as e:
        return {"error": str(e), "jwst": [], "hst": []}

    out: dict = {"jwst": [], "hst": []}
    for o in obs:
        tmin = o["t_min"]
        if tmin is None or tmin >= sn_mjd:
            continue
        coll = str(o["obs_collection"]).strip()
        rec = {
            "obs_id": str(o["obs_id"]),
            "instrument": str(o["instrument_name"]),
            "filter": str(o["filters"]),
            "t_min_mjd": float(tmin),
            "t_exptime": float(o["t_exptime"]) if o["t_exptime"] else 0.0,
            "obs_date": mjd_to_date(tmin),
        }
        if coll == "JWST":
            out["jwst"].append(rec)
        elif coll == "HST":
            out["hst"].append(rec)
    return out
