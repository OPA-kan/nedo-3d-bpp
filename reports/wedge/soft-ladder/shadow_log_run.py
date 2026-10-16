"""shadow_log_run.py TASK:LAYOUT:SEED <arm file> <out prefix> [budget]

Runs one bench episode with the arm, logging every shadow verdict the agent
asks for (the step, the item, the action, the verdict).  Writes
<out>.record.json and <out>.verdicts.json."""
import json
import os
import sys

import numpy as np

REPO = os.environ.get("REPO", "/home/user/nedo-3d-bpp")
sys.path.insert(0, REPO)
from bench.arms import make_arm  # noqa: E402
from bench.episode import run_episode  # noqa: E402
from bench.scenes import make_scene  # noqa: E402
from rule_alpha import agent as ra  # noqa: E402

LOG = []
_orig = ra.RuleAlphaAgent._shadow_verdict


def logged(self, sim, action, item):
    out = _orig(self, sim, action, item)
    placed = sum(len(c.get("packed_items", [])) for c in (self._shadow_observation or {}).get("container_list", []))
    LOG.append({"placed": placed, "item_index": int(item["index"]), "item_idx": int(action["item_idx"]),
                "container_idx": int(action["container_idx"]),
                "place_pos": [float(v) for v in np.asarray(action["place_pos"])],
                "orientation": int(action["orientation"]), "is_soft": bool(item.get("is_soft")),
                "verdict": {k: (float(v) if isinstance(v, (float, np.floating)) else v) for k, v in out.items()
                            if k in ("transport_ok", "settle_ok", "drift_xy", "angle_deg", "ok", "settle_steps")}})
    return out


ra.RuleAlphaAgent._shadow_verdict = logged

if __name__ == "__main__":
    task, layout, seed = sys.argv[1].split(":")
    spec = open(sys.argv[2]).read().strip()
    out = sys.argv[3]
    budget = float(sys.argv[4]) if len(sys.argv) > 4 else 4.5
    scene = make_scene(int(seed), layout, task.upper())
    arm = make_arm(spec)
    rec = run_episode(scene, arm, policy_budget=budget)
    json.dump(rec, open(out + ".record.json", "w"), default=float)
    json.dump(LOG, open(out + ".verdicts.json", "w"))
    m = rec["metrics"]
    print(rec["scene"], "placed", m["placed_count"], "soft", m["soft_count"], "covered", m["soft_covered"], "tmax", m["policy_time_max"], "verdicts", len(LOG))
