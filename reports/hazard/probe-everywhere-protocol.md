# Rung 2: probe-everywhere selection (preregistration)

Written before the arm exists and before any wave runs. Ladder context:
rung 1 (attribute filter) closed inert
(`reports/hazard/attribute-filter-protocol.md`); rung 3 (learned
proposer) is blocked on the post-shake instrument by ledger rule.
Rung 2 does not depend on the instrument and can be waved now.

## The hypothesis

The shipped guard (`PHYSICS_PROBE_MODE=guard_quiet`) uses real physics
only as a **veto**, and only on the ~20% of steps where the calibrated
safety logit falls below its trigger: it probes the incumbent, and when
the incumbent predicts unsafe it probes alternatives in shipped-score
order and plays the first that predicts safe. Physics never *chooses*
between two candidates that both look fine.

Rung 2 asks whether physics should select rather than veto: probe the
top-K candidates every step and play the best physics-verified one.

## The constraint that shapes the design, measured not assumed

The official evaluation reports a max policy time of **6.992 s** for the
shipped guard build against a `policy_timeout` of **8.0 s** on the
harder task set (`simulator/configs`, some cases 10.0 s)
-- `docs/OFFICIAL_SCORE_LOG.md`. Headroom is roughly **1.0 s on the
worst step**, and the guard's own contribution to that worst step was
+0.44 s. A timeout does not degrade gracefully: `EvaluationApp` falls
back to `env.action_space.sample()`, a random action, which on a late
board is a probable death.

So probe-everywhere cannot be additive. Any version that spends a fresh
budget on every step is disqualified before it is measured. The arm is
therefore specified as a **reallocation**: the probe budget is taken
from the step's existing search budget, and the probe loop is
deadline-aware, aborting cleanly with whatever verdicts it has rather
than overrunning.

## The arm

`PHYSICS_PROBE_MODE=probe_all`, a new value alongside
`off`/`guard`/`guard_quiet`. Default stays `guard_quiet`; the new value
is inert unless set, so the shipped agent is unchanged until an
adoption is licensed by this protocol's gates.

Behaviour, fixed here so it cannot drift to fit a result:

1. Compute the shipped candidate ranking exactly as today. No change to
   scoring, anchors, ordering or fallbacks.
2. Take the top K candidates (K frozen at 4 -- see budget below).
3. Probe each with `physics_probe_settle`, the same clone the guard
   uses, in shipped-score order, stopping early when the deadline
   guard trips.
4. Among probed candidates that predict SAFE, play the one with the
   highest shipped score. Ties broken by smaller predicted settle
   displacement, then by the shipped order -- so the arm degrades to
   today's behaviour when physics separates nothing.
5. If no probed candidate predicts safe, fall through to the shipped
   `guard_quiet` behaviour for that step (probe further alternatives in
   score order, play the first safe one, incumbent stands otherwise).
   Never refuse.
6. If pybullet is missing or a probe raises, the step plays the shipped
   trajectory bit-identically. Same fail-safe contract as the guard.

Budget, as source literals not knobs, matching how the guard's caps are
already frozen:

- `PHYSICS_PROBE_ALL_MAX_PROBES = 4`
- `PHYSICS_PROBE_ALL_SECONDS = 0.6`, clamped to the shipped policy
  deadline minus a reserve
- the loop must check the remaining deadline before EVERY probe and
  abort with partial verdicts rather than start one it cannot finish

## Gates (frozen; all must pass for adoption)

**T -- timing, disqualifying.** Across the wave, max policy time must
stay at or below the shipped build's max plus 0.30 s, and no step may
exceed 80% of its case's `policy_timeout`. A single overrun fails the
arm outright regardless of every other number: a random-action fallback
is not a trade we make for score.

**S -- survival, primary.** Pooled placed items must be non-inferior to
`guard_quiet` on the same streams: `placed(probe_all) >= placed(guard_quiet)`
pooled, and paired per-stream losses must not exceed wins.

**D -- deaths.** Physical deaths (topple + slide terminal channels) must
not increase pooled.

**K -- kinetic energy, from the instrument audit.** The recorded
end-of-episode `shake_peak_kinetic_energy` must not worsen by more than
10% pooled against `guard_quiet`. The guard itself worsened this by 24%
while improving shift and topple, and peak KE is the one local proxy
that has ever moved with an official component; an arm that buys
survival by making the pile more energetic is not obviously a gain.
This gate is why it is preregistered rather than reported.

**N -- negative control.** An arm identical to `probe_all` but selecting
the WORST-scoring safe candidate instead of the best must do worse than
`probe_all` on S. If it does not, the selection rule is not what is
producing any effect, and the arm is not adopted whatever S says.

## Data

Fresh streams, not any stream already adjudicated. >= 5 configs x
{guard_quiet, probe_all, probe_all_worst} x 3 replicates, arms run as
concurrent groups so wall-clock load is symmetric across arms -- the
agent's search is time budgeted and asymmetric load is a confound, as
the v2 post-shake stream showed.

## Adoption

Only if T, S, D, K and N all pass. Adoption moves the default and the
optimizer fingerprint's `behaviour_sha256` with it, per the standing
ritual. If any gate fails the arm stays off, the wave is recorded as a
closed negative, and the finding is written up the way the attribute
filter's inert verdict was.
