#!/bin/bash
S=/tmp/claude-0/-home-user-nedo-3d-bpp/c555f0d0-1382-515f-857e-e77257cc9f93/scratchpad
R=/home/user/nedo-3d-bpp/.claude/worktrees/agent-afceb3611e7dfc390
PY=/home/user/nedo-3d-bpp/.venv312/bin/python
cd $R
for p in "ship-dense-a ac_dense ac0_dense" "ship-hard-a ac_hard ac0_hard" "ship-core-a ac_core ac0_core"; do
  set -- $p
  echo "### $1"
  $PY $S/judge2.py reports/bench/$1 $S/$2 | sed 's/^/  margin2: /'
  $PY $S/judge2.py reports/bench/$1 $S/$3 | sed 's/^/  margin0: /'
  $PY $S/cmp_dirs.py reports/bench/$1 $S/$2 $S/$3 2>&1 | grep -v argv
done
