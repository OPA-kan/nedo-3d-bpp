"""ci_tab.py <base_dir> <new_dir> [--by mix|count|soft_share|priority_rate|demand] [--full]: per-scene placed /
threshold, fill (the evaluator's tolerant fill), the re-plan's pick, topples and the optimize seconds for two
records, the paired platform price per scene, and a breakdown by a scene-spec key (the suite's mix, the count,
the soft share, the priority rate, the demand band)."""
import collections
import glob
import json
import os
import sys

sys.path.insert(0, "/home/user/nedo-3d-bpp/.claude/worktrees/agent-a0a8cf4b6c63d51aa")
from bench.platform_score import score_episode  # noqa: E402

base, new = sys.argv[1], sys.argv[2]
by_key = sys.argv[sys.argv.index("--by") + 1] if "--by" in sys.argv else ""
full = "--full" in sys.argv


def load(d):
    out = {}
    for f in sorted(glob.glob(os.path.join(d, "a-*.json"))):
        r = json.load(open(f))
        out[os.path.basename(f)[:-5]] = r
    return out


def short(token):
    if not token or token == "base":
        return "base"
    side = token.split("@")[0]
    if side != "dense":
        return side
    if "priority_rows" in token:
        return "edge+strip"
    if "max_height" in token or "soft_layers" in token:
        return "edge"
    return "dense"


def demand_band(d):
    return "<0.35" if d < 0.35 else "0.35-0.45" if d < 0.45 else "0.45-0.55" if d < 0.55 else ">=0.55"


B, N = load(base), load(new)
rows = []
print("| scene | items (thr) | base placed / soft / prio | new placed / soft / prio | pick base -> new | fill base -> new | topples | optimize s base -> new | price delta |")
print("|---|---:|---|---|---|---|---|---|---:|")
for k in sorted(N):
    r, rb = N[k], B.get(k)
    if rb is None:
        continue
    m, mb = r["metrics"], rb["metrics"]
    thr = m["total_items"] // 2 + 1
    s, sb = score_episode(r), score_episode(rb)
    cs, csb = m.get("count_secure") or {}, mb.get("count_secure") or {}
    spec = r.get("scene_spec") or {}
    row = dict(scene=k, items=m["total_items"], thr=thr, placed=m["placed_count"], placed_b=mb["placed_count"],
               counted=s["counted"], counted_b=sb["counted"], fill=s["fill"], fill_b=sb["fill"],
               score=s["score"], score_b=sb["score"], topples=m.get("shake_topples"), topples_b=mb.get("shake_topples"),
               opt=m.get("optimize_seconds", 0.0), opt_b=mb.get("optimize_seconds", 0.0),
               pick=short(cs.get("chosen")), pick_b=short(csb.get("chosen")), fill_first=cs.get("fill_first"),
               spec=spec, soft=m["soft_count"], soft_b=mb["soft_count"], prio=m["priority_count"], prio_b=mb["priority_count"])
    rows.append(row)
    if full or abs(row["score"] - row["score_b"]) > 1e-9:
        print(f"| {k} | {row['items']} ({thr}) | {row['placed_b']}{' X' if row['counted_b'] else ''} / {row['soft_b']} / {row['prio_b']} | "
              f"{row['placed']}{' X' if row['counted'] else ''} / {row['soft']} / {row['prio']} | {row['pick_b']} -> {row['pick']}{' (fill-first)' if row['fill_first'] else ''} | "
              f"{row['fill_b']:.1f} -> {row['fill']:.1f} | {row['topples_b']} -> {row['topples']} | {row['opt_b']:.1f} -> {row['opt']:.1f} | {row['score'] - row['score_b']:+.2f} |")
n = len(rows)
if not n:
    sys.exit(0)
print()
print(f"scenes {n}: counted {sum(r['counted_b'] for r in rows)} -> {sum(r['counted'] for r in rows)}, "
      f"placed {sum(r['placed_b'] for r in rows) / n:.1f} -> {sum(r['placed'] for r in rows) / n:.1f}, "
      f"fill {sum(r['fill_b'] for r in rows) / n:.2f} -> {sum(r['fill'] for r in rows) / n:.2f}, "
      f"topples {sum(r['topples_b'] or 0 for r in rows)} -> {sum(r['topples'] or 0 for r in rows)}, "
      f"optimize s mean {sum(r['opt_b'] for r in rows) / n:.1f} -> {sum(r['opt'] for r in rows) / n:.1f} "
      f"max {max(r['opt_b'] for r in rows):.1f} -> {max(r['opt'] for r in rows):.1f}, "
      f"picks base {collections.Counter(r['pick_b'] for r in rows)} new {collections.Counter(r['pick'] for r in rows)}")
if by_key:
    groups = collections.defaultdict(list)
    for r in rows:
        key = r["items"] if by_key == "count" else demand_band(r["spec"].get("demand", 0.0)) if by_key == "demand" else r["spec"].get(by_key)
        groups[key].append(r)
    print()
    print(f"| {by_key} | n | counted base -> new | placed | fill | score base -> new (delta) | up / down | optimize s mean (max) base -> new |")
    print("|---|---:|---|---|---|---|---|---|")
    for key in sorted(groups, key=lambda k: str(k)):
        g = groups[key]
        m = len(g)
        d = [r["score"] - r["score_b"] for r in g]
        print(f"| {key} | {m} | {sum(r['counted_b'] for r in g)} -> {sum(r['counted'] for r in g)} | "
              f"{sum(r['placed_b'] for r in g) / m:.1f} -> {sum(r['placed'] for r in g) / m:.1f} | "
              f"{sum(r['fill_b'] for r in g) / m:.1f} -> {sum(r['fill'] for r in g) / m:.1f} | "
              f"{sum(r['score_b'] for r in g) / m:.2f} -> {sum(r['score'] for r in g) / m:.2f} ({sum(d) / m:+.2f}) | "
              f"{sum(1 for x in d if x > 1e-9)} / {sum(1 for x in d if x < -1e-9)} | "
              f"{sum(r['opt_b'] for r in g) / m:.1f} ({max(r['opt_b'] for r in g):.1f}) -> {sum(r['opt'] for r in g) / m:.1f} ({max(r['opt'] for r in g):.1f}) |")
