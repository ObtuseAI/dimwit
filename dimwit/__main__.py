"""Enable `python -m dimwit <cmd>`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dimwit.cli import main  # noqa: E402

raise SystemExit(main(sys.argv[1:]))
