from __future__ import annotations

import sys

from scripts.capture import ekris_clean_capture as clean_capture


def test_clean_capture_backend_uses_printwindow_not_framebuffer():
    backend = clean_capture._capture_backend()

    assert backend["tier"] == "printwindow"
    assert backend["proc"] == "UnrealEditor"
    assert backend["reason"] == "locked-desktop-safe"


def _run() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    failed = []
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
        except Exception as exc:
            failed.append((test.__name__, exc))
            print(f"  FAIL  {test.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(_run())
