"""Build a diagnostic submission that surrenders every item of the named tasks.

    python3 scripts/build_diagnostic_submission.py B          -> dist/submit_diag_b.zip
    python3 scripts/build_diagnostic_submission.py C          -> dist/submit_diag_c.zip
    python3 scripts/build_diagnostic_submission.py B C        -> dist/submit_diag_bc.zip

The build is the ordinary one (scripts/build_rule_alpha_submission.py) with
``DIAGNOSTIC_SURRENDER_TASKS`` in the copied ``agent.py`` set to the tasks
named; the repository's ``submission/agent.py`` keeps the empty tuple.  The
zip holds a top-level ``submit/`` directory like the scored builds.  See
reports/wedge/stability-lattice.md for what the platform result then reads.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_rule_alpha_submission import STACK_POLICY, build, zip_dir  # noqa: E402


def main() -> int:
    tasks = tuple(sorted({t.upper() for t in sys.argv[1:]}))
    if not tasks or any(t not in ("A", "B", "C") for t in tasks):
        print(__doc__)
        return 2
    out = build((ROOT / "dist" / "submit").resolve(), STACK_POLICY.resolve())
    agent = out / "agent.py"
    text = agent.read_text(encoding="utf-8")
    new, n = re.subn(r"^DIAGNOSTIC_SURRENDER_TASKS: tuple = \(\)$",
                     f"DIAGNOSTIC_SURRENDER_TASKS: tuple = {tasks!r}", text, flags=re.M)
    if n != 1:
        raise SystemExit("DIAGNOSTIC_SURRENDER_TASKS line not found once in the copied agent.py")
    agent.write_text(new, encoding="utf-8")
    archive = zip_dir(out, (ROOT / "dist" / f"submit_diag_{''.join(tasks).lower()}.zip").resolve())
    print(f"diagnostic build surrendering {tasks}: {archive} ({archive.stat().st_size / 1e6:.1f} MB); "
          f"{out} holds the patched copy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
