#!/bin/bash
# run_an.sh <name> <extra-overrides>: the ladder-only analytic arm (arm_light_c.txt)
# on the 48 core C scenes, with probe.py's bridge counters; writes <name>.json/.log here
D=/home/user/nedo-3d-bpp/reports/wedge/bridge-generator
cd /home/user/nedo-3d-bpp
SC=$(ls reports/bench/gate0-core | sed 's/.json//' | grep "^c-")
python3 $D/probe.py $D/$1.json $D/arm_light_c.txt "$2" $SC > $D/$1.log 2>&1
