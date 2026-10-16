"""Build a diagnostic submission.

    python3 scripts/build_diagnostic_submission.py B          -> dist/submit_diag_b.zip
    python3 scripts/build_diagnostic_submission.py C          -> dist/submit_diag_c.zip
    python3 scripts/build_diagnostic_submission.py B C        -> dist/submit_diag_bc.zip
    python3 scripts/build_diagnostic_submission.py A:planner  -> dist/submit_diag_a_planner.zip
    python3 scripts/build_diagnostic_submission.py A:dryrun   -> dist/submit_diag_a_dryrun.zip

A task letter surrenders every item of that task from the first call
(``DIAGNOSTIC_SURRENDER_TASKS`` in the copied ``agent.py``).  ``A:<form>``
keeps Task A playing but with its offline phase changed
(``DIAGNOSTIC_TASK_A_OVERRIDES``): ``planner`` runs the row planner alone
(no ladder dry-run), ``dryrun`` the ladder's dry-run alone (no planner),
``fastplan`` the shipped pair with the planner's variants cut to the first
one.  The repository's ``submission/agent.py`` keeps the empty values.  The
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

A_FORMS = {
    "planner": dict(offline_dry_run=False),
    "dryrun": dict(offline_planner=""),
    "fastplan": dict(plan_variants="first", plan_layouts=1),
}


def main() -> int:
    args = [a.strip() for a in sys.argv[1:] if a.strip()]
    tasks = tuple(sorted({a.upper() for a in args if ":" not in a}))
    forms = [a.split(":", 1)[1].lower() for a in args if a.upper().startswith("A:")]
    if not args or any(t not in ("A", "B", "C") for t in tasks) or any(f not in A_FORMS for f in forms) or len(forms) > 1:
        print(__doc__)
        return 2
    out = build((ROOT / "dist" / "submit").resolve(), STACK_POLICY.resolve())
    agent = out / "agent.py"
    text = agent.read_text(encoding="utf-8")
    if tasks:
        text, n = re.subn(r"^DIAGNOSTIC_SURRENDER_TASKS: tuple = \(\)$",
                          f"DIAGNOSTIC_SURRENDER_TASKS: tuple = {tasks!r}", text, flags=re.M)
        if n != 1:
            raise SystemExit("DIAGNOSTIC_SURRENDER_TASKS line not found once in the copied agent.py")
    if forms:
        text, n = re.subn(r"^DIAGNOSTIC_TASK_A_OVERRIDES: dict = \{\}$",
                          f"DIAGNOSTIC_TASK_A_OVERRIDES: dict = {A_FORMS[forms[0]]!r}", text, flags=re.M)
        if n != 1:
            raise SystemExit("DIAGNOSTIC_TASK_A_OVERRIDES line not found once in the copied agent.py")
    agent.write_text(text, encoding="utf-8")
    tag = "".join(tasks).lower() + ("_a_" + forms[0] if forms else "")
    archive = zip_dir(out, (ROOT / "dist" / f"submit_diag_{tag.strip('_')}.zip").resolve())
    print(f"diagnostic build (surrender {tasks}, A form {forms or None}): {archive} "
          f"({archive.stat().st_size / 1e6:.1f} MB); {out} holds the patched copy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
