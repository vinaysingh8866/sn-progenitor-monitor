"""Compatibility shim: ``python monitor.py`` runs the ``sn-monitor`` CLI.

install.sh copies this file next to the data directory; the package itself must be
installed (``pip install .``) or importable from the checkout this file lives in.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from sn_progenitor_monitor.cli import main
except ImportError:  # running from a checkout without installing
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from sn_progenitor_monitor.cli import main

if __name__ == "__main__":
    sys.exit(main())
