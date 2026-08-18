"""Run the bundled evaluation with the post-shake recorder installed.

A thin wrapper: it installs `scripts/postshake_capture` (a no-op unless
NEDO_POSTSHAKE_CAPTURE is set) and then hands control to the bundled
`simulator/scripts/run_test.py` main(), unchanged. Nothing under
`simulator/` is modified; the harness invokes this instead of
run_test.py when it wants the capture.

Must be invoked with the simulator directory as cwd, exactly as the
bundled runner is, so `src.ground_handling` imports resolve. The
repository root is added to sys.path only to reach
`scripts.postshake_capture`.
"""

from __future__ import annotations

import pathlib
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SIMULATOR = _REPO_ROOT / "simulator"
if str(_SIMULATOR) not in sys.path:
    sys.path.insert(0, str(_SIMULATOR))

from scripts.postshake_capture import install  # noqa: E402

install()

sys.path.insert(0, str(_SIMULATOR / "scripts"))
from run_test import main  # noqa: E402


if __name__ == "__main__":
    main()
