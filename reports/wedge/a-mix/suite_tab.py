"""The dense-mix-a suite's scenes: mix, shares, count, container, demand."""
import collections
import sys

sys.path.insert(0, "/home/user/nedo-3d-bpp/.claude/worktrees/agent-a0a8cf4b6c63d51aa")

from bench.scenes import build_suite

scenes = build_suite(sys.argv[1] if len(sys.argv) > 1 else "dense-mix-a")
print("| scene | mix | items | soft share | prio rate | container (l x w x h) | shelf | demand | draws |")
print("|---|---|---:|---:|---:|---|---|---:|---:|")
for s in scenes:
    sp = s.spec
    l, w, h = sp["dims"][0]
    print(f"| {s.name} | {sp['mix']} | {len(s.items)} | {sp['soft_share']} | {sp['priority_rate']} | {l} x {w} x {h} | "
          f"{sp['shelves']} | {sp['demand']:.3f} | {sp.get('draws', 1)} |")
print()
print("mixes", collections.Counter(s.spec["mix"] for s in scenes))
print("counts", collections.Counter(len(s.items) for s in scenes))
print("soft", collections.Counter(s.spec["soft_share"] for s in scenes))
print("prio", collections.Counter(s.spec["priority_rate"] for s in scenes))
print("shelf", collections.Counter(s.spec["shelves"] for s in scenes))
print("draws", collections.Counter(s.spec.get("draws", 1) for s in scenes))
ds = sorted(s.spec["demand"] for s in scenes)
print("demand min/median/max", ds[0], ds[len(ds) // 2], ds[-1])
