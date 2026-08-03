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
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(AGENT, arcname=f"{args.dir_name}/agent.py")

    print(f"built: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

