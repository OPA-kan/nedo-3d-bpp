# Design record: two-timescale learning and diverse rule-based actors

Date: 2026-08-25 (design review, fourth round — after match 005
promoted the generation-2 champion). Direction set by the project
owner; this file freezes the decisions.

## 1. In-match online adaptation (short-timescale learning)

The league so far learns only *between* generations. The next object
is an agent that also learns *within* one episode:

    pi_{theta, phi_t}   theta: the frozen champion body
                        phi_t: a small adapter updated during the match

Frozen decisions:

- **The champion body is never touched in-match.** theta stays exactly
  the promoted generation; phi starts at 0 every episode and is
  **discarded when the episode ends**. Racehorse framing: bloodline =
  frozen champion, race-day conditioning = the adapter. This keeps
  "the same name means the same policy" true for league accounting.
- **Adapter = preference-head calibration only.** phi is a delta on
  each ensemble member's final linear head (input: the penultimate
  activation z(s,a)); the backbone and all other weights are frozen.
  One update is cheap and catastrophic forgetting has no surface to
  bite. This is online preference *calibration*, not online RL.
- **Updates come only from counterfactual comparisons.** "The action I
  executed survived, therefore it was right" is exactly the noise the
  preference objective was built to avoid. The only teacher an
  in-match update may use is a physically executed A/B fork whose
  terminal comparison yields a **strict dominance winner** under the
  same 5-head rule as everything else (ties and censored terminals
  update nothing). No scalar reward, no advantage estimate — the
  (s, A, B, B>A) pair goes straight into one-to-few pairwise logistic
  SGD steps on phi, with a hard trust region ||phi|| <= rho.
- **Fork gating and budget.** Normal turns are inference-only. A fork
  is spent only when the adapted model is genuinely uncertain (top
  alternate probability inside a band around the switch threshold) and
  a per-episode fork budget remains. When a fork resolves, its winner
  is executed (physics outranks the model at that state); when it does
  not resolve, the adapted argmax stands and nothing is learned.
- **SLA status: exhibition track, not production.** Mid-match terminal
  forks are search work, so the online clone lives outside the SLA —
  like pi0-search it can never gate, veto, or be promoted. Exhibition
  results are reported, not acted on by the gate.
- **Long-term memory path.** If online adaptation proves valuable, its
  fork outcomes are ordinary preference pairs; they flow into the next
  generation's corpus and are distilled *permanently* into pi_{t+1}.
  Short-term memory (phi, discarded) -> long-term memory (next
  generation), two timescales, one objective.

### Preregistered experiment: champion vs its online clone

One exhibition match, declared here before it runs:

- Arms: **pi2-pref-w6 frozen** (プリフヒバリ, current champion) vs
  **pi2-pref-w6-online** (same weights + in-match adapter; stable name
  シュンヒバリ, new 冠名 シュン = race-day-adaptation line).
- Same 10 frozen eval streams, same seeds, deterministic pairing —
  the standard match harness in a new non-promoting `exhibition` mode.
- Read-out: paired dominance relations clone-vs-champion. Wins >
  losses is evidence that online adaptation adds value *at equal
  weights*; the per-fork update log (probability before/after, winner)
  is the training-side diagnostic either way.
- Eval-set accounting: this is **one** extra look at the frozen eval
  set, preregistered here; exhibition outcomes never feed promotion,
  and no matrix or hyperparameter may be tuned from them.

## 2. Diverse rule-based actors (experience-generation side)

The champion converging means the teacher corpus's state distribution
narrows toward champion-visited boards. The standing principle is
**diversity lives in experience generation, not in the reward**: run
deliberately different-minded actors to *reach different states*, and
let the same terminal-dominance teacher label whatever happens there.

Actor stable (thoroughly rule-based, no learning, cheap):

| actor | 名 | inductive bias |
|---|---|---|
| rule-grid | グリッドオー | snap placements to a fixed lattice; regular, spacious boards |
| rule-lowcog | テイジュウシン | minimize resulting center-of-mass height; dense bottom layers |
| rule-edge | カベヅタイ | hug walls and corners; perimeter-first boards |

Frozen decisions:

- These are **studs, not champions**: their job is to generate states
  the champion line would never reach. They may appear in exhibitions
  but never gate, and their boards only matter as future teacher
  roots.
- They act by *re-ranking the same physically screened candidate set*
  every other arm uses (selection heuristics over safe root
  candidates), so all safety/物理 contracts are unchanged.
- The reference hand-written phasing (fixed orientation, back-to-front
  L-shaped approach, grid placement, drop from height) maps onto
  placement heuristics only. Its "sort arrivals by Priority/Hard/Soft"
  phase does **not** apply to Task C (arrival order is not ours to
  choose); it becomes relevant only for Tasks A/B.
- **Season 1's preregistered waves 5-14 are untouched.** Mixing
  diversity actors into the teacher matrix is a training-recipe change
  and will be preregistered for season 2 (or a separate side corpus),
  justified by training-side coverage diagnostics (height histograms,
  wall-contact rates, state-fingerprint diversity of the corpus) —
  never by league or spectator observations, per the read-only
  contract.

## 3. What ships now

1. `OnlineAdapterPolicy` (frozen ensemble + per-member head adapter,
   pairwise-logistic online updates, trust region, full event log).
2. Runner policy `online`: adapted scoring each turn; gated,
   budget-capped A/B terminal forks; fork winner executed; adapter
   events in the episode record (spectator can replay them).
3. Runner policies `rule-grid`, `rule-lowcog`, `rule-edge`.
4. League `exhibition` mode: full paired report, never promotes,
   never touches the registry.
5. Names registered (シュンヒバリ; グリッドオー/テイジュウシン/カベヅタイ).
6. The preregistered exhibition above, dispatched once the code lands.
