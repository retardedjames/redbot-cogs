"""Dev mode configuration — shared by all cogs.

Set DEV_MODE = False before going to production to hide version labels.
"""
import pathlib
import subprocess

# ── Toggle this to disable version labels in all cogs ─────────────────────────
DEV_MODE = True
# ──────────────────────────────────────────────────────────────────────────────


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(pathlib.Path(__file__).parent),
             "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return "dev"


_VERSION = _git_sha() if DEV_MODE else ""
DEV_LABEL = f"  [{_VERSION}]" if DEV_MODE and _VERSION else ""
