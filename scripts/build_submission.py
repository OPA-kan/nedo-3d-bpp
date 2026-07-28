from __future__ import annotations

import argparse
import pathlib
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
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(AGENT, arcname="agent.py")

    print(f"built: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

