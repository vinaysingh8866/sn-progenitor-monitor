"""Orchestration: fetch candidates, resolve distances and archive coverage, keep state, report, notify.

Layout of the data directory (``$SN_MONITOR_DIR``, default ``~/.sn-progenitor-monitor``):
  state.json          seen SNe with cached distance and last-alerted coverage counts
  hits.jsonl          append-only hit log
  last_run.log        last-run summary (same text as the report)
  latest_report.txt   human-readable report of the last run
  HITS/HIT_*.txt      one plaintext alert per hit
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .archives import host_distance_mpc, mjd, query_pre_explosion
from .scrape import LOOKBACK_DAYS, MAG_MAX, Supernova, fetch_sne

DEFAULT_DATA_DIR = "~/.sn-progenitor-monitor"
ENV_VAR = "SN_MONITOR_DIR"

# ------------------------------ tunables ------------------------------
DIST_MAX_MPC = 35.0  # only flag if host within this distance


def resolve_data_dir(override: str | os.PathLike | None = None) -> Path:
    """``override`` > ``$SN_MONITOR_DIR`` > default. The directory is not created here."""
    raw = override or os.environ.get(ENV_VAR) or DEFAULT_DATA_DIR
    return Path(raw).expanduser()


@dataclass(frozen=True)
class DataDir:
    root: Path

    @property
    def state(self) -> Path:
        return self.root / "state.json"

    @property
    def hits(self) -> Path:
        return self.root / "hits.jsonl"

    @property
    def last_run(self) -> Path:
        return self.root / "last_run.log"

    @property
    def report(self) -> Path:
        return self.root / "latest_report.txt"

    @property
    def hit_files(self) -> Path:
        return self.root / "HITS"

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)


def load_state(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            pass
    return {"seen": {}}


def save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2))


@dataclass
class Hit:
    sn: Supernova
    dist_mpc: float
    coverage: dict
    block: str = ""

    def to_record(self, logged_at: datetime) -> dict:
        return {
            "logged_at": logged_at.isoformat(),
            "sn": self.sn.to_dict(),
            "dist_mpc": self.dist_mpc,
            "coverage": self.coverage,
        }


@dataclass
class RunResult:
    started: datetime
    candidates: list[Supernova]
    new_hits: list[Hit] = field(default_factory=list)
    nearby_no_cov: list[Supernova] = field(default_factory=list)
    far_skipped: list[Supernova] = field(default_factory=list)
    unknown_dist: list[Supernova] = field(default_factory=list)
    report: str = ""

    def hits_json(self) -> list[dict]:
        return [h.to_record(self.started) for h in self.new_hits]


def desktop_notify(title: str, message: str, sound: bool = False) -> bool:
    """macOS notification banner via osascript. Returns False when skipped or failed."""
    if shutil.which("osascript") is None:
        return False
    safe_msg = message.replace("\\", "\\\\").replace('"', '\\"')
    safe_title = title.replace("\\", "\\\\").replace('"', '\\"')
    sound_clause = ' sound name "Glass"' if sound else ""
    try:
        subprocess.run(
            ["osascript", "-e", f'display notification "{safe_msg}" with title "{safe_title}"{sound_clause}'],
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def render_hit_block(sn: Supernova, dist_mpc: float | None, cov: dict) -> str:
    d_str = f"{dist_mpc:.1f} Mpc" if dist_mpc else "unknown"
    lines = [
        f"  {sn.name:<11s} {sn.type:<5s} mag={sn.mag:.1f} date={sn.date:<14s} host={sn.host}  D={d_str}",
        f"    RA={sn.ra:.4f}  Dec={sn.dec:.4f}",
    ]
    for label, key in (("JWST", "jwst"), ("HST", "hst")):
        if cov.get(key):
            lines.append(f"    {label} pre-explosion ({len(cov[key])}):")
            for o in cov[key][:8]:
                lines.append(
                    f"      {o['obs_date']}  {o['instrument']}  {o['filter']}  "
                    f"exp={o['t_exptime']:.0f}s  obs_id={o['obs_id']}"
                )
    return "\n".join(lines)


def write_hit_file(data: DataDir, hit: Hit, now: datetime) -> Path:
    """Drop a plaintext alert file in ``HITS/``.

    macOS TCC blocks launchd-spawned processes from writing to ~/Desktop, so files go in
    the data directory instead; the notification banner is the actual alert.
    """
    data.hit_files.mkdir(parents=True, exist_ok=True)
    sn = hit.sn
    path = data.hit_files / f"HIT_{sn.name}_{now.strftime('%Y%m%d')}.txt"
    body = [
        "JWST/HST PRE-EXPLOSION PROGENITOR HIT",
        "=" * 50,
        "",
        f"SN:           {sn.name}",
        f"Type:         {sn.type}",
        f"Discovered:   {sn.date}",
        f"Magnitude:    {sn.mag}",
        f"Host:         {sn.host}",
        f"Distance:     {hit.dist_mpc:.1f} Mpc",
        f"Position:     RA={sn.ra:.5f}  Dec={sn.dec:.5f}",
        "",
        "Pre-explosion archive coverage:",
        hit.block,
        "",
        f"Logged: {now.isoformat()}Z",
        "Full record: $SN_MONITOR_DIR/hits.jsonl",
    ]
    path.write_text("\n".join(body))
    return path


def build_report(result: RunResult, seen: dict) -> str:
    r = result
    lines = [
        f"SN Progenitor Monitor — run {r.started.isoformat()}Z",
        f"  Lookback: {LOOKBACK_DAYS} d   Mag<{MAG_MAX}   D<{DIST_MAX_MPC} Mpc",
        f"  Candidates fetched: {len(r.candidates)}",
        f"  Within distance cutoff with coverage hits: {len(r.new_hits)} (NEW), "
        f"nearby-no-coverage: {len(r.nearby_no_cov)}, "
        f"far-skipped: {len(r.far_skipped)}, unknown-dist: {len(r.unknown_dist)}",
    ]
    if r.new_hits:
        lines += ["", "=" * 72, "NEW HITS — pre-explosion HST/JWST imaging exists", "=" * 72]
        for hit in r.new_hits:
            lines += ["", hit.block]
    else:
        lines += ["", "No new hits this run."]
        if r.nearby_no_cov:
            lines += ["", "Nearby SNe under monitoring (no archive coverage yet):"]
            for sn in r.nearby_no_cov[:10]:
                d = seen.get(sn.name, {}).get("dist_mpc")
                d_str = f"{d:.1f} Mpc" if d is not None else "unknown"
                lines.append(
                    f"  {sn.name:<11s} {sn.type:<5s} mag={sn.mag:.1f} date={sn.date:<14s} host={sn.host}  D={d_str}"
                )
    return "\n".join(lines)


def notify_result(result: RunResult) -> None:
    r = result
    if r.new_hits:
        n_jw = sum(1 for h in r.new_hits if h.coverage.get("jwst"))
        first = r.new_hits[0].sn
        desktop_notify(
            f"NEW HIT: {first.name} ({first.type}) in {first.host[:30]}",
            f"{len(r.new_hits)} hit(s), {n_jw} with JWST pre-coverage. See HITS/ in the data directory.",
            sound=True,
        )
    elif r.nearby_no_cov:
        names = ", ".join(s.name for s in r.nearby_no_cov[:3])
        more = f" (+{len(r.nearby_no_cov) - 3} more)" if len(r.nearby_no_cov) > 3 else ""
        desktop_notify(
            "SN Monitor — nearby SNe under watch",
            f"{len(r.nearby_no_cov)} nearby SN(e) without coverage: {names}{more}",
        )
    else:
        desktop_notify(
            "SN Monitor — no new candidates",
            f"Checked {len(r.candidates)} SNe; none nearby + within archive coverage.",
        )


def run(
    data_dir: Path,
    *,
    dry_run: bool = False,
    notify: bool = True,
    now: datetime | None = None,
    candidates: list[Supernova] | None = None,
) -> RunResult:
    """One monitoring pass.

    ``dry_run`` performs the lookups but writes nothing and sends no notification.
    ``candidates`` bypasses the network fetch (used by tests).
    """
    now = now or datetime.utcnow()
    data = DataDir(data_dir)
    state = load_state(data.state)
    seen: dict = state.setdefault("seen", {})

    sne = candidates if candidates is not None else fetch_sne(now=now)
    result = RunResult(started=now, candidates=sne)

    for sn in sne:
        prev = seen.setdefault(sn.name, {})
        dist = prev.get("dist_mpc")
        if dist is None and "dist_resolved" not in prev:
            dist = host_distance_mpc(sn.host)
            prev["dist_resolved"] = True
            prev["dist_mpc"] = dist
        if dist is None:
            result.unknown_dist.append(sn)
            continue
        if dist > DIST_MAX_MPC:
            result.far_skipped.append(sn)
            continue

        # Coverage check runs every time, in case new MAST products landed.
        cov = query_pre_explosion(sn.ra, sn.dec, mjd(sn.discovered))
        n_jw, n_hs = len(cov.get("jwst", [])), len(cov.get("hst", []))
        prev.update(last_check=now.isoformat(), last_n_jwst=n_jw, last_n_hst=n_hs)

        if n_jw == 0 and n_hs == 0:
            result.nearby_no_cov.append(sn)
            continue

        already = prev.get("alerted_n_jwst") == n_jw and prev.get("alerted_n_hst") == n_hs
        if already:
            continue
        hit = Hit(sn, dist, cov, render_hit_block(sn, dist, cov))
        result.new_hits.append(hit)
        if not dry_run:
            prev["alerted_n_jwst"], prev["alerted_n_hst"] = n_jw, n_hs
            data.ensure()
            with data.hits.open("a") as f:
                f.write(json.dumps(hit.to_record(now)) + "\n")

    result.report = build_report(result, seen)
    if dry_run:
        return result

    state["last_run"] = now.isoformat()
    data.ensure()
    save_state(data.state, state)
    data.report.write_text(result.report)
    data.last_run.write_text(result.report)
    for hit in result.new_hits:
        write_hit_file(data, hit, now)
    if notify:
        notify_result(result)
    return result
