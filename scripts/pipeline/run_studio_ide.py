"""Launch Dimwit's local-only Studio IDE."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # repo root (dimwit/, ue_mcp/, scripts/)

import sys

from dimwit.studio_ide.server import serve


def _value(argv: list[str], name: str, default, cast):
    return cast(argv[argv.index(name) + 1]) if name in argv else default


def main(argv: list[str]) -> int:
    serve(port=_value(argv, "--port", 8765, int), open_browser="--no-open" not in argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
