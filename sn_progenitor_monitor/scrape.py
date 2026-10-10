"""Parse the Rochester "Latest Supernovae" location table and filter candidates."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

import requests

BISHOP_URL = "http://www.rochesterastronomy.org/snimages/snlocations.html"
HTTP_TIMEOUT = 60

# ------------------------------ tunables ------------------------------
LOOKBACK_DAYS = 90  # how far back in the list to consider
MAG_MAX = 18.0  # discovery mag cutoff (proxy for nearness)
CC_TYPES = frozenset({"II", "IIb", "IIn", "IIP", "IIL", "Ib", "Ic", "Ic-BL", "Ibc", "Ib/c", "Ib/Ic"})

# One table row of snlocations.html. Groups, in order:
#   ra_sexagesimal, dec_sexagesimal, ra_hours, dec_deg, discovery_date,
#   host, redshift, type, magnitude, name (inside <a>), survey_id
ROW_RE = re.compile(
    r"<tr><td>([^<]+)</td><td>([^<]+)</td><td>([\d.\-]+)</td><td>([\d.\-]+)</td><td>([\d/.]+)</td>"
    r"<td>([^<]*)</td><td[^>]*>([\d.\-]+)</td><td>([^<]*)</td><td>([\d.\-]+)</td>"
    r"<td><a href=\"[^\"]*\"[^>]*>([^<]+)</a></td><td>([^<]*)</td></tr>"
)


@dataclass(frozen=True)
class Supernova:
    """One supernova row from the location table."""

    name: str
    type: str
    date: str  # discovery date as listed, e.g. "2026/09/30.512"
    discovered: datetime  # parsed discovery date (day precision)
    mag: float
    ra: float  # degrees
    dec: float  # degrees
    host: str
    survey_id: str

    @property
    def is_core_collapse(self) -> bool:
        return self.type in CC_TYPES

    def to_dict(self) -> dict:
        d = asdict(self)
        d["discovered"] = self.discovered.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Supernova:
        d = dict(d)
        d["discovered"] = datetime.fromisoformat(d["discovered"])
        return cls(**d)


def parse_rows(html: str) -> list[Supernova]:
    """Parse every table row the regex matches. Rows with unparsable numbers/dates are skipped."""
    out: list[Supernova] = []
    for _ra_s, _dec_s, ra_h, dec_d, date, host, _z, t, mag, name, surv in ROW_RE.findall(html):
        try:
            m = float(mag)
            ra_deg = float(ra_h) * 15.0
            dec_deg = float(dec_d)
            disc = datetime.strptime(date.split(".")[0], "%Y/%m/%d")
        except ValueError:
            continue
        out.append(
            Supernova(
                name=name.strip(),
                type=t.strip(),
                date=date,
                discovered=disc,
                mag=m,
                ra=ra_deg,
                dec=dec_deg,
                host=host.strip(),
                survey_id=surv.strip(),
            )
        )
    return out


def filter_candidates(
    sne: list[Supernova],
    *,
    now: datetime | None = None,
    lookback_days: int = LOOKBACK_DAYS,
    mag_max: float = MAG_MAX,
) -> list[Supernova]:
    """Keep recent core-collapse SNe brighter than ``mag_max``, sorted by magnitude (brightest first)."""
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=lookback_days)
    kept = [sn for sn in sne if sn.is_core_collapse and sn.discovered >= cutoff and sn.mag <= mag_max]
    kept.sort(key=lambda sn: sn.mag)
    return kept


def fetch_html(url: str = BISHOP_URL, timeout: float = HTTP_TIMEOUT) -> str:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def fetch_sne(*, now: datetime | None = None) -> list[Supernova]:
    """Download the list and return the filtered candidates."""
    return filter_candidates(parse_rows(fetch_html()), now=now)
