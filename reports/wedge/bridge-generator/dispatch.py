import json, subprocess, sys
# dispatch.py armfile suite out shards  (ref = claude/rl-packing-policy-ftogt3-bridge-gen)
S = "/home/user/nedo-3d-bpp/reports/wedge/bridge-generator/"
arm = open(S + sys.argv[1]).read().strip()
suite, out, shards = sys.argv[2], sys.argv[3], sys.argv[4]
body = json.dumps({'ref': 'claude/rl-packing-policy-ftogt3-bridge-gen', 'inputs': {
    'arm': arm, 'suite': suite, 'sim': 'physics', 'out': out, 'shards': shards, 'budget': '4.5'}})
p = subprocess.run(["gh", "api", "-X", "POST",
                    "repos/OPA-kan/nedo-3d-bpp/actions/workflows/bench-run.yml/dispatches",
                    "--input", "-"], input=body, text=True, capture_output=True)
print(out, p.returncode, p.stdout[-200:], p.stderr[-200:])
