#!/bin/bash
# wait.sh <run_id>...: poll every 120 s until every run is completed
until [ -z "$(for r in "$@"; do s=$(gh api repos/OPA-kan/nedo-3d-bpp/actions/runs/$r --jq '.status' 2>/dev/null); [ "$s" = "completed" ] || echo $r; done)" ]; do
  sleep 120
done
for r in "$@"; do echo "$r $(gh api repos/OPA-kan/nedo-3d-bpp/actions/runs/$r --jq '.conclusion')"; done
