"""dispatch_all.py: the short-budget measurement, 14 bench runs on the a-count branch."""
import json, subprocess, time
D = "/tmp/claude-0/-home-user-nedo-3d-bpp/c555f0d0-1382-515f-857e-e77257cc9f93/scratchpad/acount/"
R = "/home/user/nedo-3d-bpp/.claude/worktrees/agent-afceb3611e7dfc390/reports/bench/arms/"
jobs = []
for name in ("ship", "v51", "fix"):
    for b in (40, 60):
        jobs.append((f"acb{b}{name}", D + f"arm_{name}{b}.txt"))
jobs.append(("acountfix", R + "arm_acountfix_a.txt"))
for out, armfile in jobs:
    arm = open(armfile).read().strip()
    for suite in ("dense-a", "core-a"):
        body = json.dumps({"ref": "claude/rl-packing-policy-ftogt3-a-count", "inputs": {
            "arm": arm, "suite": suite, "sim": "physics", "out": f"reports/bench/{out}-{suite}", "shards": "6",
            "budget": "4.5"}})
        p = subprocess.run(["gh", "api", "-X", "POST",
                            "repos/OPA-kan/nedo-3d-bpp/actions/workflows/bench-run.yml/dispatches", "--input", "-"],
                           input=body, text=True, capture_output=True)
        print(out, suite, p.returncode, p.stderr[-200:], flush=True)
        time.sleep(3)
