from __future__ import annotations

import argparse
import pathlib
import re
import zipfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
AGENT = ROOT / "agent" / "agent.py"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=ROOT / "dist" / "submission.zip",
    )
    parser.add_argument(
        "--dir-name",
        default="submit",
        help=(
            "Top-level directory inside the archive. The platform requires the"
            " zip to contain an agent DIRECTORY holding agent.py, not a flat"
            " agent.py (simulator/README.md '応募用ファイルの作成'). A flat"
            " archive is rejected at upload."
        ),
    )
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KNOB=VALUE",
        help=(
            "Bake a knob default into the built copy. The evaluation"
            " platform runs agent.py with no environment, so a knob that"
            " ships off is off there no matter what the ablation arms say;"
            " this is how a specific configuration gets submitted without"
            " flipping the repository default first. Recorded in the"
            " printed manifest so the submitted configuration is"
            " reconstructable."
        ),
    )
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    source = AGENT.read_text(encoding="utf-8")
    applied = []
    for assignment in args.set:
        knob, _, value = assignment.partition("=")
        knob = knob.strip()
        value = value.strip()
        # The knob reads are wrapped across lines, so match structurally
        # rather than by a flat prefix.
        pattern = re.compile(
            r'(os\.environ\.get\(\s*"' + re.escape(knob) + r'"\s*,\s*)"[^"]*"'
        )
        source, count = pattern.subn(
            lambda m: f'{m.group(1)}"{value}"', source, count=1
        )
        if count != 1:
            raise SystemExit(f"knob not found in agent.py: {knob!r}")
        applied.append((knob, value))

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{args.dir_name}/agent.py", source)

    print(f"built: {output}")
    for knob, value in applied:
        print(f"  baked default: {knob}={value}")
    if not applied:
        print("  baked default: none (repository defaults as-is)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

