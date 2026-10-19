"""dispatch.py <armfile> <suite> <out>: the bench-run.yml dispatch body for the amix branch (Task A arms: the 30 s
offline budget appended), written to body_<out>.json next to this script; the caller posts it with gh api."""
import json
import os
import sys

arm = open(sys.argv[1]).read().strip() + ",offline_budget_seconds=30"
body = {"ref": "claude/rl-packing-policy-ftogt3-amix",
        "inputs": {"arm": arm, "suite": sys.argv[2], "sim": "physics", "out": f"reports/bench/{sys.argv[3]}",
                   "shards": "6", "budget": "4.5"}}
path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"body_{sys.argv[3]}.json")
with open(path, "w") as f:
    json.dump(body, f)
print(path)
