# Literature review → the search direction (2026-08-17)

Read after the hazard line closed at its entry gate. Three papers, and
how each maps onto this repo's own adjudicated evidence.

## 1. PCT — Learning Efficient Online 3D-BPP on Packing Configuration
Trees (Zhao et al., ICLR 2022)

State is represented as the TREE OF FEASIBLE PLACEMENTS (leaf nodes =
candidate placements with geometry), not as a heightmap grid; a
pointer-attention policy scores leaves. Their finding: this
candidate-set representation beats grid CNNs and stays robust in
continuous action spaces.

**Maps onto our evidence exactly.** Decision-level features carry
signal here (safety perception AUC 0.933 live); state summaries do not
(four representations failed the 0.561 bar, and grid representations
specifically memorized container layout in the hazard training). The
board is best described by what can still be DONE in it.

## 2. ToP — Deliberate Planning of 3D Bin Packing on PCT (Zhao et al.,
IJRR 2025, arXiv:2504.04421)

MCTS over item-sequence x placement paths on the PCT. Preview items
(their analog of our visible pool) are enumerated DIRECTLY in the
tree; only the unknown future beyond the preview is collapsed into a
terminal node scored by the critic V. Path caching across adjacent
steps halves decision cost. Gains over the reactive policy: +15.8 to
+18 utilization points (75.0 -> 90.8 with lookahead; 77.0 -> 95.0 with
a 10-item buffer).

**The lesson for us is the DIVISION OF LABOR.** Their V works because
it only prices the tail beyond enumeration; the near future is
searched, not predicted. Our value attempts failed when asked to carry
the whole future alone. We have the same structural opportunity: the
competition's visible pool (k items) is their preview buffer, our
policy budget is 8 s/step of which the shipped agent uses ~3 s.

## 3. Fast stability validation (arXiv:2507.09123)

Replace physics simulation inside the decision loop with a
geometric test (center of mass within the support polygon), ms-fast,
then plan around it.

**We already own both halves**: the agent's release contract computes
support/CoM margins, and the calibrated safety model (Gate 1) is a
LEARNED fast stability validator with measured live discrimination.

## The synthesis: measured-leaf visible-pool tree search

The evidence-consistent design, differing from every closed line:

- Depth 2-3 enumeration over the ACTUAL visible pool (real future
  items, not a sampled prior), expanding with the agent's own
  candidate generator per item and a heightmap afterstate transition.
- Leaf evaluation is MEASURED, not predicted: run the candidate
  scan on the leaf board and count legal, risk-gated options per
  remaining item class — receptivity measured at the leaf, where the
  four failed representations tried to predict it at the root.
- The safety model prices physical risk along the path (its licensed
  role: perception, not control).

Distinct from closed lines: board_k reordered the CURRENT top-K by
depth-0 receptivity (mixed, unshipped); the rollout arms were depth-1
and Q-scored; temporal chunking voted on delayed plans without search.
None enumerated the visible pool to depth >= 2 with measured leaves.

Known risk, stated up front: the heightmap transition inside the
search inherits the sim-to-real gap that killed value PREDICTION. The
bet — supported by ToP's numbers — is that a transition model too
coarse to predict episode value is still good enough to ORDER a few
hundred enumerated near-futures. That bet is exactly what the paired
episode A/B measures.

## Sources

- https://openreview.net/forum?id=bfuGjlCwAq (PCT, ICLR 2022)
- https://arxiv.org/abs/2504.04421 (ToP, IJRR 2025)
- https://arxiv.org/abs/2507.09123 (fast stability validation)
- https://github.com/alexfrom0815/Online-3D-BPP-PCT (PCT code)
