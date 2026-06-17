"""Persist each lot's last-seen availability between runs.

The state is a tiny JSON map ``{"P4": true, "P2": false, ...}``. It lets us email
only on a 0->1 transition (a spot newly opening) and stay silent while a spot
remains open. When a lot closes again the stored value flips back to False, so a
*future* reopening notifies again. In CI this file is committed back to the repo
so it survives across scheduled runs.
"""

from __future__ import annotations

import json
import os
from typing import Dict

from . import config


def load_state(path: str | None = None) -> Dict[str, bool]:
    """Return the saved availability map, or {} if there is no state yet."""
    path = path or config.STATE_PATH
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        # Corrupt/unreadable state -> treat as empty rather than crash the run.
        return {}
    # Keep only boolean values keyed by lot code.
    return {str(k): bool(v) for k, v in data.items()} if isinstance(data, dict) else {}


def save_state(state: Dict[str, bool], path: str | None = None) -> None:
    """Write the availability map atomically-ish (write then replace)."""
    path = path or config.STATE_PATH
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)
