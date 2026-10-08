"""platform_predict.py <record_dir>...: what the platform's four components
would read under the hypothesis H1, from a suite's records.

H1 (the simulator README, "評価指標"): the soft score is the share of
the stream's soft items placed and not under cargo of another attribute;
the placement score the share of the stream's priority items placed,
not under cargo of another attribute, and in the priority container when
one exists; the cog score 100 x (1 - the mass-weighted centre of mass
over the container's height); every one over the counted episodes.  The
denominators are the whole stream, placed or not: a decline at 60 % of
the stream caps the soft score near 60 whatever the load.  Per
directory: the placed fraction, the H1 soft and placement predictions,
the cog reading, and the plain shares of what was placed, so the
suite's own numbers can be put against the official feedback of the
build that produced them."""
import glob
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from bench.scenes import make_hard_scene, make_scene  # noqa: E402


def _scene(spec):
    if spec.get("layout") == "hard" or "hard" in spec["name"]:
        return make_hard_scene(spec["seed"], spec["task"])
    return make_scene(spec["seed"], spec["layout"], spec["task"])


def predict(d: str) -> dict:
    rows = []
    for f in sorted(glob.glob(str(pathlib.Path(d) / "[abc]-*.json"))):
        r = json.load(open(f))
        m = r["metrics"]
        scene = _scene(r["scene_spec"])
        items = scene.items
        n = len(items)
        thr = n // 2 + 1
        soft_total = sum(1 for i in items if i.get("is_soft"))
        prio_total = sum(1 for i in items if i.get("is_prioritized"))
        soft_ok = m["soft_count"] - m.get("soft_covered", 0)
        prio_ok = m["priority_count"] - m.get("priority_covered", 0) - m.get("priority_misrouted", 0)
        counted = m["placed_count"] >= thr
        rows.append({
            "counted": counted, "fraction": m["placed_fraction"], "fill": m["fill_volume"],
            "soft_h1": 100.0 * soft_ok / soft_total if soft_total else 100.0,
            "prio_h1": 100.0 * prio_ok / prio_total if prio_total else 100.0,
            "soft_of_placed": soft_ok / max(m["soft_count"], 1), "prio_of_placed": prio_ok / max(m["priority_count"], 1),
            "cog": 100.0 * (1.0 - m.get("com_z_above_floor_ratio", 0.0)),
            "topples": m.get("shake_topples", 0), "contact_covered": m.get("contact_covered", 0),
            "shake_max": m.get("shake_max_shift", 0.0), "shake_mean": m.get("shake_mean_shift", 0.0),
            # stability readings: the shake's displacements against the
            # validator's 0.3 m threshold, and the share that did not topple
            "stab_max": 100.0 * max(0.0, 1.0 - m.get("shake_max_shift", 0.0) / 0.3),
            "stab_mean": 100.0 * max(0.0, 1.0 - m.get("shake_mean_shift", 0.0) / 0.3),
            "stab_topple": 100.0 * (1.0 - m.get("shake_topples", 0) / max(m["placed_count"], 1)),
        })
    if not rows:
        return {}
    c = [r for r in rows if r["counted"]] or rows
    out = {
        "dir": pathlib.Path(d).name, "episodes": len(rows), "counted": sum(1 for r in rows if r["counted"]),
        "fraction": float(np.mean([r["fraction"] for r in rows])), "fill": float(np.mean([r["fill"] for r in rows])),
        # the platform zeroes the four components under the threshold
        "soft_h1": float(np.mean([r["soft_h1"] if r["counted"] else 0.0 for r in rows])),
        "prio_h1": float(np.mean([r["prio_h1"] if r["counted"] else 0.0 for r in rows])),
        "cog_h1": float(np.mean([r["cog"] if r["counted"] else 0.0 for r in rows])),
        "soft_of_placed": float(np.mean([r["soft_of_placed"] for r in c])),
        "prio_of_placed": float(np.mean([r["prio_of_placed"] for r in c])),
        "topples_per_episode": float(np.mean([r["topples"] for r in c])),
        "shake_max": float(np.mean([r["shake_max"] for r in c])),
        "shake_mean": float(np.mean([r["shake_mean"] for r in c])),
        "stab_max": float(np.mean([r["stab_max"] if r["counted"] else 0.0 for r in rows])),
        "stab_mean": float(np.mean([r["stab_mean"] if r["counted"] else 0.0 for r in rows])),
        "stab_topple": float(np.mean([r["stab_topple"] if r["counted"] else 0.0 for r in rows])),
    }
    return out


def main():
    print("| dir | n | counted | fraction | fill | soft H1 | placement H1 | cog H1 | soft ok of placed | prio ok of placed | topples/ep | shake max | shake mean | stab(max) | stab(mean) | stab(topple) |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for d in sys.argv[1:]:
        p = predict(d)
        if not p:
            continue
        print(f"| {p['dir']} | {p['episodes']} | {p['counted']} | {p['fraction']:.3f} | {p['fill']:.2f} | {p['soft_h1']:.1f} | {p['prio_h1']:.1f} | {p['cog_h1']:.1f} | {p['soft_of_placed']:.3f} | {p['prio_of_placed']:.3f} | {p['topples_per_episode']:.2f} | {p['shake_max']:.3f} | {p['shake_mean']:.3f} | {p['stab_max']:.1f} | {p['stab_mean']:.1f} | {p['stab_topple']:.1f} |")


if __name__ == "__main__":
    main()
