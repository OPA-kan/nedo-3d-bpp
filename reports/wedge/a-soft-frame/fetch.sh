#!/bin/bash
# fetch.sh <run_id> <out_name>: the run's shard artifacts, unauthenticated, into reports/bench/<out_name>/
set -e
run=$1; out=$2
REPO=/home/user/nedo-3d-bpp/.claude/worktrees/agent-a67fbe9a22b0417ad
DL=/tmp/claude-0/-home-user-nedo-3d-bpp/c555f0d0-1382-515f-857e-e77257cc9f93/scratchpad/sf/dl_$run
rm -rf "$DL"; mkdir -p "$DL"; cd "$DL"
ids=$(curl -sS "https://api.github.com/repos/OPA-kan/nedo-3d-bpp/actions/runs/$run/artifacts" | python3 -I -c "import json,sys; print(' '.join(str(a['id']) for a in json.load(sys.stdin)['artifacts']))")
echo "run $run artifacts: $ids"
for id in $ids; do
  curl -sSL -o $id.zip "https://api.github.com/repos/OPA-kan/nedo-3d-bpp/actions/artifacts/$id/zip"
  mkdir -p x_$id && unzip -qo $id.zip -d x_$id
done
mkdir -p "$REPO/reports/bench/$out"
n=0
for f in $(find "$DL" -name 'a-*.json'); do cp "$f" "$REPO/reports/bench/$out/"; n=$((n+1)); done
echo "copied $n records into reports/bench/$out"
ls "$REPO/reports/bench/$out" | wc -l
