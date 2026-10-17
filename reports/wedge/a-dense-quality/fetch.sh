#!/bin/bash
# fetch.sh <run_id>: the run's shard artifacts, unauthenticated, into reports/bench/<artifact name without the
# shard suffix>/ (the bench-run workflow names each shard's artifact after the run directory).
set -e
run=$1
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
DL=/tmp/claude-0/-home-user-nedo-3d-bpp/c555f0d0-1382-515f-857e-e77257cc9f93/scratchpad/ci/dl_$run
rm -rf "$DL"; mkdir -p "$DL"; cd "$DL"
curl -sS "https://api.github.com/repos/OPA-kan/nedo-3d-bpp/actions/runs/$run/artifacts" > artifacts.json
python3 -I -c "import json; [print(a['id'], a['name']) for a in json.load(open('artifacts.json'))['artifacts']]" > list.txt
echo "run $run artifacts:"; cat list.txt
while read -r id name; do
  curl -sSL -o "$id.zip" "https://api.github.com/repos/OPA-kan/nedo-3d-bpp/actions/artifacts/$id/zip"
  mkdir -p "x_$id" && unzip -qo "$id.zip" -d "x_$id"
  out=$(echo "$name" | sed -E 's#^reports/bench/##; s#-shard[-_]?[0-9]+$##; s#[-_][0-9]+$##')
  mkdir -p "$REPO/reports/bench/$out"
  n=0
  for f in $(find "x_$id" -name 'a-*.json'); do cp "$f" "$REPO/reports/bench/$out/"; n=$((n+1)); done
  echo "  $name -> reports/bench/$out: $n records"
done < list.txt
