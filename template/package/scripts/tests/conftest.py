"""Make `from lib ...` work when pytest is started from the repo root.

`lib.*` lives in template/package/scripts/. Do not put template/package on
sys.path here: that would import the template `workspace` module and leak it
into tests that stub a temporary workspace.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
