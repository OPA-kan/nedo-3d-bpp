"""Render the league spectator template into a deployable static room."""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any


def _safe_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )


def render_html(
    template: str, match: dict[str, Any], live_status: dict[str, Any]
) -> str:
    if "__MATCH_DATA__" not in template or "__LIVE_STATUS__" not in template:
        raise ValueError("spectator template placeholders are missing")
    return (
        template.replace("__MATCH_DATA__", _safe_json(match), 1)
        .replace("__LIVE_STATUS__", _safe_json(live_status), 1)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=pathlib.Path, required=True)
    parser.add_argument("--match", type=pathlib.Path, required=True)
    parser.add_argument("--live-status", type=pathlib.Path, required=True)
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()
    match = json.loads(args.match.read_text(encoding="utf-8"))
    live = json.loads(args.live_status.read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    html = render_html(
        args.template.read_text(encoding="utf-8"), match, live
    )
    (args.output_dir / "index.html").write_text(html, encoding="utf-8")
    (args.output_dir / "live.json").write_text(
        json.dumps(live, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "match.json").write_text(
        json.dumps(match, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({"cells": len(match.get("cells", {})),
                      "stage": live.get("stage")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
