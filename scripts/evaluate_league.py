"""Evaluate a challenger arm against the policy league on frozen episodes.

Modes:
- ``--bootstrap NAME``: no registry exists yet; the provided manifests
  become the anchor (and initial champion) pi_0 and a fresh registry is
  written.
- default: load the registry, run the asymmetric promotion decision
  (main gate vs champion, collapse detector vs the rest), write the
  match report; with ``--promote-on-pass`` also write the updated
  registry when the challenger is promoted.
- ``--audit-anchor``: verify the provided manifests reproduce the
  anchor's stored outcomes bit-identically (determinism audit).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.league import (  # noqa: E402
    DEFAULT_PARAMS,
    episode_outcome,
    load_registry,
    new_registry,
    promote,
    promotion_decision,
)


def collect_outcomes(
    manifest_root: pathlib.Path,
) -> dict[str, dict[str, Any]]:
    outcomes = {}
    for path in sorted(manifest_root.rglob("manifest.json")):
        cell = path.parent.parent.name if path.parent.name == "rollout" \
            else path.parent.name
        payload = json.loads(path.read_text(encoding="utf-8"))
        outcomes[cell] = episode_outcome(payload)
    if not outcomes:
        raise ValueError(f"no manifest.json under {manifest_root}")
    return outcomes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-root", type=pathlib.Path, required=True)
    parser.add_argument("--registry", type=pathlib.Path, required=True)
    parser.add_argument("--challenger-name", required=True)
    parser.add_argument("--source", required=True,
                        help="Actions run id or provenance string")
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--audit-anchor", action="store_true")
    parser.add_argument("--promote-on-pass", action="store_true")
    parser.add_argument(
        "--exhibition", action="store_true",
        help="full paired report, but never promote and never write a"
             " registry (SLA-exempt arms: online clones, rule studs)",
    )
    parser.add_argument("--report", type=pathlib.Path, required=True)
    parser.add_argument("--registry-out", type=pathlib.Path)
    for key, value in DEFAULT_PARAMS.items():
        parser.add_argument(
            f"--{key.replace('_', '-')}", type=float, default=value,
        )
    args = parser.parse_args()
    params = {key: getattr(args, key) for key in DEFAULT_PARAMS}
    outcomes = collect_outcomes(args.manifest_root)
    args.report.parent.mkdir(parents=True, exist_ok=True)

    if args.bootstrap:
        if args.registry.exists():
            raise SystemExit("registry already exists; refusing bootstrap")
        registry = new_registry(
            args.challenger_name, outcomes, source=args.source,
        )
        registry_out = args.registry_out or args.registry
        registry_out.parent.mkdir(parents=True, exist_ok=True)
        registry_out.write_text(
            json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        report = {
            "contract": "league_bootstrap_v1",
            "anchor": args.challenger_name,
            "eval_cells": registry["eval_cells"],
            "outcomes": outcomes,
        }
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"bootstrap": args.challenger_name,
                          "cells": len(outcomes)}, indent=2))
        return 0

    registry = load_registry(args.registry)
    if args.audit_anchor:
        anchor = next(
            member for member in registry["members"]
            if member["role"] == "anchor"
        )
        drift = {
            cell: {
                "stored": anchor["outcomes"][cell]["heads"],
                "observed": outcomes[cell]["heads"],
            }
            for cell in anchor["outcomes"]
            if outcomes.get(cell, {}).get("heads")
            != anchor["outcomes"][cell]["heads"]
        }
        report = {
            "contract": "league_anchor_audit_v1",
            "anchor": anchor["name"],
            "cells": len(anchor["outcomes"]),
            "drifted_cells": drift,
            "reproduced": not drift,
        }
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"anchor_reproduced": not drift,
                          "drifted": sorted(drift)}, indent=2))
        return 0 if not drift else 1

    if args.exhibition and args.promote_on_pass:
        raise SystemExit("--exhibition and --promote-on-pass are exclusive")
    decision = promotion_decision(outcomes, registry, params)
    decision["challenger"] = args.challenger_name
    decision["source"] = args.source
    if args.exhibition:
        # exhibitions report everything but decide nothing: the arm is
        # outside the SLA (or a diversity stud) and can never gate,
        # veto, or hold the title
        decision["exhibition"] = True
        decision["promoted"] = False
    args.report.write_text(
        json.dumps(decision, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if decision["promoted"] and args.promote_on_pass:
        updated = promote(
            registry, args.challenger_name, outcomes, source=args.source,
        )
        registry_out = args.registry_out or args.registry
        registry_out.parent.mkdir(parents=True, exist_ok=True)
        registry_out.write_text(
            json.dumps(updated, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps({
        "challenger": args.challenger_name,
        "promoted": decision["promoted"],
        "main_gate": decision["main_gate"],
        "league_collapses": sorted(
            name for name, check in decision["league_checks"].items()
            if check["collapsed"]
        ),
        "benchmarks": {
            name: standing["standing"]
            for name, standing in decision.get("benchmarks", {}).items()
        },
        "vs_champion": decision["matches"][decision["champion"]]["counts"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
