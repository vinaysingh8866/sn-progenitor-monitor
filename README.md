# sn-progenitor-monitor

A daily watcher that reports when a nearby core-collapse supernova appears in a galaxy that HST or JWST had already imaged.

Pre-explosion imaging is how supernova progenitor stars are identified, and the window to claim one is short. The monitor scrapes the Rochester "Latest Supernovae" location table, keeps the recent core-collapse events brighter than a magnitude cut, asks NED for the host distance, and asks MAST whether HST or JWST observed that position before the discovery date. Hits are appended to a log, written to a plaintext report, and (on macOS) raised as a desktop notification.

## Install

```bash
pip install .                 # scraper + CLI (requests only)
pip install ".[archives]"     # + astropy/astroquery for the NED and MAST lookups
```

The `sn-monitor` command is installed with the package. `python monitor.py` and `python -m sn_progenitor_monitor` are equivalent.

## Usage

```bash
sn-monitor                         # one pass: fetch, check archives, update state, notify
sn-monitor run --dry-run           # look everything up but write no state, hits or report
sn-monitor run --json              # print the new hits of this pass as JSON
sn-monitor run --no-notify         # skip the desktop notification
sn-monitor report                  # print the report from the last run
sn-monitor --data-dir /path run    # use another data directory (overrides $SN_MONITOR_DIR)
```

`run` is the default subcommand, so `sn-monitor --dry-run` works too. `--once` is accepted for explicitness in cron wrappers; a pass always runs once and exits.

The data directory is `$SN_MONITOR_DIR`, default `~/.sn-progenitor-monitor`.

## Scheduled runs (macOS launchd)

```bash
./install.sh      # installs the package into $PYTHON, writes and loads a daily LaunchAgent, runs once
./uninstall.sh    # unloads and removes the agent; data is left in place
```

`install.sh` installs the package with `$PYTHON` (default: `python3` on the PATH), copies the `monitor.py` shim to the data directory, writes a LaunchAgent from `launchagent.plist.template`, loads it, and starts a first run. macOS blocks launchd jobs from reading `~/Desktop` and `~/Documents`, which is why nothing is run from the repository checkout. Logs go to `$SN_MONITOR_DIR/cron.log`.

Linux: run `sn-monitor` from cron. Notifications use `osascript` and are skipped when it is unavailable.

## Tunables

| Name | Module | Default | Meaning |
|---|---|---|---|
| `LOOKBACK_DAYS` | `scrape.py` | 90 | How far back in the list to look |
| `MAG_MAX` | `scrape.py` | 18.0 | Discovery magnitude cut, a proxy for distance |
| `CC_TYPES` | `scrape.py` | II, IIb, IIn, Ib, Ic, ... | Classifications treated as core-collapse |
| `DIST_MAX_MPC` | `monitor.py` | 35 | Only flag hosts within this distance |
| `SEARCH_RADIUS_ARCMIN` | `archives.py` | 1.5 | MAST cone radius around the supernova |

## Output

| File | Content |
|---|---|
| `state.json` | Supernovae already seen, with cached distance and the coverage counts last alerted on |
| `hits.jsonl` | Append-only record of every hit with the matching HST/JWST observation IDs |
| `latest_report.txt` | Human-readable summary of the last run (`sn-monitor report`) |
| `HITS/HIT_<name>_<date>.txt` | One plaintext alert per hit |

A supernova is alerted on again only if the number of pre-explosion JWST or HST observations changes.

## Layout

```
sn_progenitor_monitor/
  scrape.py     table parsing (regex -> Supernova dataclass) and candidate filter
  archives.py   NED host distance, MAST pre-explosion coverage
  monitor.py    one monitoring pass: state, hits log, report, notification
  cli.py        argparse entry point (sn-monitor)
monitor.py      shim so `python monitor.py` keeps working
tests/          pytest suite; network calls are mocked, fixtures/snlocations_sample.html is a sample table
```

## Development

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check .
pytest
```

## License

MIT. Copyright (c) 2026 Vinay Singh.
