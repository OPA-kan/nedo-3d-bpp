# c001-k1 under the true envelope: the wall moves, then becomes real

Date: 2026-08-03. `measure_dead_end_branch.py`, flag `ANCHOR_TRUE_ENVELOPE=1`
(now the shipped default, so the replays exercise the submitted agent).
Branch JSONs alongside this file. Companion to `summary.md` (the ablation)
and `reports/task-c/wall-is-not-a-wall.md` (the box-envelope autopsy).

Both arms replay deterministic trajectories, and the true-envelope
trajectory diverges from step 0 — so "step N" below is the same position in
the episode, not the same board. Comparisons are between episodes.

## Step by step

| step | candidates | safe | survivors/killers | total_slots | next_item_slots | conc_max | extinct |
|---|---:|---:|---|---:|---:|---:|---:|
| 18 | 68 | 8 | 8 / 0 | 24 | 10 | 0.080 | 2 |
| 19 | 130 | 8 | 8 / 0 | 4–6 | 1 | 0.333–0.369 | 2 |
| 20 | 35 | 8 | 0 / 8 | — | 0 | 1.000 | **7** |
| 21 | **0** | 0 | — | — | — | — | — |

Box-envelope reference at the same episode positions: step 18 was 4/4
survivors with total_slots 15, step 19 was 8/8 **killers** with
next_item_slots 0.

## Four findings

**1. The old wall was an artifact.** The box-envelope step-19 wall (8/8
killers) does not exist on the true-envelope trajectory: step 19 is 8/8
survivors and the live policy reaches it without rescue
(`replay_rescues=[]`). The state classification built on the box trajectory
measured the anchor bug, not the board.

**2. The new terminal at step 21 is certified, this time properly.** Two
independent instruments agree: exhaustive generator enumeration returns 0
candidates, and the dense probe (2.5 cm lattice over the full container
cross-section, every support level, every orientation, geometric acceptance
against the real half-spaces) returns **0 geometric hits** for item 22.
This is the same probe that overturned the previous "certified" dead end
with 16 counterexamples. Caveats: 2.5 cm lattice resolution, one case, one
deterministic trajectory.

**3. Collapse is non-gradual.** total_slots runs 24 → 4–6 → 0 in two
steps, and step 20 is uniform annihilation: all 8 legal placements of item
21 leave **all seven classes extinct** (conc 1.000). There is no gradually
impoverishing board for a value function to detect early; the cliff spans
the final two decisions.

**4. Within-step feature separation exists but has nothing to predict.**
Step 19 is the first state ever measured where the board features split
across candidates (total_slots 6 vs 4, conc 0.333 vs 0.369 — ranks 0,2 vs
the rest). But all 8 branches survive step 19 and all merge into the same
uniform death at step 20, so the split carries no decision-relevant signal.
Pairwise accuracy is undefined (0 discordant pairs) at every step measured,
on both trajectories.

## ~~Verdict for the board-value program~~ (superseded same day — see below)

On c001-k1 there is **no board-selection problem at any measured step**:
candidates within a step are either all-alive or all-dead. The
Φ-as-tie-break line stays dead — now measured on the real search space, not
the artifact. Φ(s) retains its state-level role (the F1 re-run: the fix
moved R and Hall on 16/43 snapshots, correlations stay weak, max |ρ|
0.336). What remains actionable at the step-21 terminal is not selection
but termination: the episode ends by the poison fixed-coordinate fallback
`[0,0,0.25]` on a board where nothing fits. Whether that unsafe terminal
action costs score relative to any cleaner refusal is now the live
question, plus the same certification for c000-k1's new terminal.

## Correction (2026-08-03, horizon labels): the selection problem exists

The verdict above used `kills_stream` — 1-step survivorship — as the label
and asserted "the split has nothing to predict" without horizon labels.
That conflation is exactly the error TASK_C_BOARD_VALUE.md §0.1 documents:
static features identical, horizon outcomes split. Running the horizon
analysis (top-8, horizon 6, live policy forward-play) on the true-envelope
trajectory:

| step 18 branch | score | reached | placed from branch |
|---|---:|---:|---:|
| rank 0 (live pick) | +0.238 | 21 | +2 |
| ranks 3, 6 | +0.236 | 20 | +1 |
| **ranks 5, 7 (orient 3)** | **−0.44** | **23** | **+4** |

All eight step-18 candidates carry byte-identical discrete features
(total_slots 24, conc 0.080), yet their terminal depths span 20–23: the
choice at step 18 is worth ±2–3 placed, every continuation still ends
`true_dead_end`, and the live ranker prefers a worse branch (the reached-23
branches sit at rank 5 and 7). At step 19 the split narrows to 20 vs 21 —
step 18 is the decisive branching point. Ledger:
`c001-k1-selection-problem-exists-features-are-blind` (supersedes
`taskc-collapse-is-non-gradual-tie-break-line-dead`).

So the corrected verdict is the theory's own §0.1 position, now replicated
on the real search space: a board-selection problem exists, candidate-derived
discrete counts are blind to it, and the geometric-pocket observation unit
(stage 3: corridor r_z, support σ_z) has a live, quantified target.
Caveats: forward play depends on the deadline-driven policy under
measurement CPU load; one case; top-8 by score.

## Second correction (2026-08-03, fixed instrument): the split was noise

Both instrument defects fixed (candidates pinned once from a reference
replay; the reference's action sequence replayed verbatim per branch;
per-branch digest match recorded). Validation passed inside the run:
8/8 branch boards match the reference digest. Result: **all top-8 safe
candidates at step 18 reach exactly step 21** (+3 placed, `true_dead_end`),
including two spatially distinct groups (orient 5 at +0.81,−0.42 and an
orient-1 cluster at −0.03..−0.05,−0.60). `choice_matters: false`.

The 20/21/23 split in the section above was replay contamination — the
defective replay re-ran the deadline-driven policy and each "branch"
started from a different board. Ledger:
`c001-k1-step18-choice-does-not-matter` (and
`horizon-labels-were-replay-contaminated` for the defect itself).

Standing conclusion for c001-k1: with the true envelope, 21 placed is
invariant to late-game choice (steps 18–20 measured); the terminal at 21
is a certified dead end. Unmeasured: early-game choices (0–17), other
replay basins, candidates beyond the top-8.
