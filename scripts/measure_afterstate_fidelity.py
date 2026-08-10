"""
How far can the physics-free afterstate model be trusted?

`fast_afterstate_env.py` enumerates placements ~1500x faster than settling
each one, which is what makes a training loop thinkable. The speed is
worthless if the boards it predicts are not the boards physics produces, so
this measures the gap rather than assuming it.

Two questions, deliberately separated, because they fail differently:

  GEOMETRY  does the drop model put the item where physics leaves it?
            measured as the settle displacement between the predicted
            release pose and the settled pose.

  SAFETY    of the placements the model calls legal, how many does physics
            accept? A model that admits unsafe poses trains a policy to
            seek them, so the false-accept rate is the number that decides
            whether a learned ranker can be trusted off this environment.

The replay dataset already carries the labels: every sampled candidate was
executed and its settle recorded. So this reads them rather than paying for
new physics, and the sampling weights come with it -- the rows are an
unequal-probability sample, so rates are reweighted and an unweighted count
would over-represent whatever the strata over-sampled.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import math
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_ROOT = ROOT / "reports" / "replay-dataset"


def load_rows(dataset_root: pathlib.Path):
    for path in sorted(glob.glob(f"{dataset_root}/**/*.jsonl", recursive=True)):
        split = None
        manifest = pathlib.Path(path).parent / "manifest.json"
        if manifest.exists():
            try:
                payload = json.loads(manifest.read_text(encoding="utf-8"))
                split = payload.get("split")
                if payload.get(
                    "sampling_mode", "stratified_random"
                ) != "stratified_random":
                    continue
            except json.JSONDecodeError:
                split = None
        # final_holdout is opened once, at the end of the protocol, and not
        # by an instrument like this one.
        if split == "final_holdout":
            continue
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def summarize(rows) -> dict:
    kinds = collections.Counter()
    weighted_safe = collections.defaultdict(float)
    weighted_total = collections.defaultdict(float)
    displacement = collections.defaultdict(list)
    rotation = collections.defaultdict(list)

    for row in rows:
        physical = row.get("physical") or {}
        kind = row.get("kind") or "unknown"
        weight = float(
            (row.get("sampling") or {}).get("sampling_weight") or 1.0
        )
        safe = physical.get("is_placed_safe")
        if safe is None:
            continue
        kinds[kind] += 1
        weighted_total[kind] += weight
        if safe:
            weighted_safe[kind] += weight
        for name, source in (
            ("d_xy", physical.get("d_xy")),
            ("d_z", physical.get("d_z")),
            ("d_norm", physical.get("d_norm")),
        ):
            if isinstance(source, (int, float)):
                displacement[(kind, name)].append(float(source))
        theta = physical.get("delta_theta_deg")
        if isinstance(theta, (int, float)):
            rotation[kind].append(float(theta))

    report = {"rows": int(sum(kinds.values())), "by_kind": {}}
    for kind, count in sorted(kinds.items()):
        total = weighted_total[kind]
        entry = {
            "rows": int(count),
            "weighted_safe_rate": (
                weighted_safe[kind] / total if total > 0 else None
            ),
        }
        for name in ("d_xy", "d_z", "d_norm"):
            values = displacement.get((kind, name)) or []
            if values:
                values_sorted = sorted(values)
                entry[name] = {
                    "median": statistics.median(values_sorted),
                    "p90": values_sorted[int(0.90 * (len(values_sorted) - 1))],
                    "max": values_sorted[-1],
                }
        angles = rotation.get(kind) or []
        if angles:
            angles_sorted = sorted(angles)
            entry["delta_theta_deg"] = {
                "median": statistics.median(angles_sorted),
                "p90": angles_sorted[int(0.90 * (len(angles_sorted) - 1))],
                "max": angles_sorted[-1],
            }
        report["by_kind"][kind] = entry
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=pathlib.Path, default=DEFAULT_ROOT)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()

    report = summarize(load_rows(args.dataset_root))
    if report["rows"] == 0:
        print("no labelled rows found", file=sys.stderr)
        return 1

    print(f"labelled candidates: {report['rows']}\n")
    print(
        f"{'kind':22s} {'rows':>6s} {'safe(weighted)':>15s} "
        f"{'d_xy p90':>9s} {'d_z p90':>8s} {'dtheta p90':>11s}"
    )
    for kind, entry in report["by_kind"].items():
        rate = entry["weighted_safe_rate"]
        print(
            f"{kind[:22]:22s} {entry['rows']:6d} "
            f"{('-' if rate is None else f'{rate:.3f}'):>15s} "
            f"{entry.get('d_xy', {}).get('p90', float('nan')):9.4f} "
            f"{entry.get('d_z', {}).get('p90', float('nan')):8.4f} "
            f"{entry.get('delta_theta_deg', {}).get('p90', float('nan')):11.2f}"
        )
    print(
        "\nrelease rows are the ones the fast model reproduces: it drops a"
        "\npose and accepts it under the release contract, exactly as those"
        "\nrows were generated. Their safe rate is the ceiling on how much a"
        "\nranker trained in that environment can be trusted, and their"
        "\ndisplacement is how far the predicted board sits from the settled"
        "\none. Rates are reweighted by sampling_weight; the rows are an"
        "\nunequal-probability sample and a raw count would report the"
        "\nstrata rather than the population."
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nwrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
