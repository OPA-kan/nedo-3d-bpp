#!/bin/bash
# poll.sh <run_id>...: every 5 minutes, the status of the bench runs, until all are completed.
LOG=/tmp/claude-0/-home-user-nedo-3d-bpp/c555f0d0-1382-515f-857e-e77257cc9f93/scratchpad/ci/poll2.log
RUNS="$*"
N=$#
for i in $(seq 1 60); do
  done=0; out=""
  for run in $RUNS; do
    s=$(gh api repos/OPA-kan/nedo-3d-bpp/actions/runs/$run --jq .status 2>&1)
    c=$(gh api repos/OPA-kan/nedo-3d-bpp/actions/runs/$run --jq .conclusion 2>&1)
    out="$out $run:$s/$c"
    if [ "$s" = "completed" ]; then done=$((done+1)); fi
  done
  echo "$(date +%H:%M) $out" >> $LOG
  if [ $done -ge $N ]; then break; fi
  sleep 300
done
echo ALLDONE >> $LOG
