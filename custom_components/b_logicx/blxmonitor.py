#!/usr/bin/env python3

"""Compatibility wrapper — blxmonitor moved into the library package.

The real tool lives at ``b_logicx/blxmonitor.py`` so it does not put this
Home Assistant integration directory on ``sys.path`` (which would shadow
the stdlib ``select`` module via our ``select.py`` platform).

This stub only uses stdlib and re-execs the new location, so old commands
keep working:

  python3 /config/custom_components/b_logicx/blxmonitor.py -i ...
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_TARGET = Path(__file__).resolve().parent / "b_logicx" / "blxmonitor.py"

if not _TARGET.is_file():
    sys.stderr.write(f"blxmonitor not found at {_TARGET}\n")
    sys.exit(1)

os.execv(sys.executable, [sys.executable, str(_TARGET), *sys.argv[1:]])
