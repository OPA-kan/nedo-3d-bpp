# Tree search stage 1 (enforce A/B): FAIL, line closed

Run 31991555287, 63/63 episodes, negative control within every floor
(instrument clean). The arm acted -- 93 enforced swaps -- and the
gates close it: pooled placed 386 base vs 372 tree_search, paired 4W/7L,
no-harm breached on b000-k20 (-3.33 vs floor 1.97). Topple+slide
dipped 14 -> 12, but the placed cost fails direction and no-harm, so
per the protocol's symmetric closure the knob stays off.

Fifth failure of a geometry-proxy-driven intervention. The pattern is
now unambiguous: orderings computed on the heightmap geometry -- for
value prediction or for search -- do not survive contact with the
physics that actually ends episodes. The one lever not resting on that
proxy is the in-process physics probe (measured: 40 ms/candidate drop,
19 ms mini-shake, fidelity gate = reproducing Gate 1's 14 recorded
fatal actions), which is the successor line.
