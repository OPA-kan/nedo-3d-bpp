"""sort_records.py <mixed dir> <prefix> <base prefix> <suite>...: the records of several suites fetched into one
directory, moved into reports/bench/<prefix>-<suite>/ by the scene names of reports/bench/<base prefix>-<suite>/;
every record's arm must match the first's.  Prints what moved and what did not match."""
import json
import os
import shutil
import sys

mixed, prefix, base_prefix = sys.argv[1], sys.argv[2], sys.argv[3]
root = os.path.dirname(os.path.abspath(mixed))
suites = {s: set(os.listdir(os.path.join(root, f"{base_prefix}-{s}"))) for s in sys.argv[4:]}
arm = None
moved = {s: 0 for s in suites}
left = []
for f in sorted(os.listdir(mixed)):
    if not f.endswith(".json"):
        continue
    r = json.load(open(os.path.join(mixed, f)))
    arm = arm or r.get("arm")
    if r.get("arm") != arm:
        print("ARM MISMATCH", f)
    for s, names in suites.items():
        if f in names:
            os.makedirs(os.path.join(root, f"{prefix}-{s}"), exist_ok=True)
            shutil.move(os.path.join(mixed, f), os.path.join(root, f"{prefix}-{s}", f))
            moved[s] += 1
            break
    else:
        left.append(f)
print("arm:", json.dumps(arm)[-200:])
print("moved:", moved, "unmatched:", left)
for s, names in suites.items():
    missing = names - set(os.listdir(os.path.join(root, f"{prefix}-{s}")))
    print(s, "missing", sorted(missing) if missing else "none")
