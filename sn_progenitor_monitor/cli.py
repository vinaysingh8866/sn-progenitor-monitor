"""Command-line interface: ``sn-monitor [run|report]``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from . import __version__
from .monitor import DataDir, resolve_data_dir, run

COMMANDS = ("run", "report")


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--data-dir",
        metavar="DIR",
        default=argparse.SUPPRESS,
        help="data directory (overrides $SN_MONITOR_DIR; default ~/.sn-progenitor-monitor)",
    )

    parser = argparse.ArgumentParser(
        prog="sn-monitor",
        description="Watch for nearby core-collapse supernovae with pre-explosion HST/JWST imaging.",
        parents=[common],
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run", parents=[common], help="fetch the list and check archives (default)")
    p_run.add_argument("--dry-run", action="store_true", help="look things up but write no state, hits or report")
    p_run.add_argument("--once", action="store_true", help="single pass and exit (the default; explicit for cron use)")
    p_run.add_argument("--json", action="store_true", help="print new hits as JSON instead of the text report")
    p_run.add_argument("--no-notify", action="store_true", help="skip the desktop notification")

    sub.add_parser("report", parents=[common], help="print the report from the last run")
    return parser


def _normalise_argv(argv: Sequence[str]) -> list[str]:
    """Make ``run`` the default subcommand so ``sn-monitor --dry-run`` works."""
    argv = list(argv)
    if any(a in COMMANDS for a in argv) or any(a in ("-h", "--help", "--version") for a in argv):
        return argv
    return ["run", *argv]


def cmd_run(args: argparse.Namespace) -> int:
    data_dir = resolve_data_dir(getattr(args, "data_dir", None))
    result = run(data_dir, dry_run=args.dry_run, notify=not args.no_notify and not args.dry_run)
    if args.json:
        print(json.dumps(result.hits_json(), indent=2))
    else:
        print(result.report)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    data = DataDir(resolve_data_dir(getattr(args, "data_dir", None)))
    if not data.report.exists():
        print(f"no report yet in {data.root}", file=sys.stderr)
        return 1
    print(data.report.read_text())
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(_normalise_argv(sys.argv[1:] if argv is None else argv))
    if args.command == "report":
        return cmd_report(args)
    return cmd_run(args)
