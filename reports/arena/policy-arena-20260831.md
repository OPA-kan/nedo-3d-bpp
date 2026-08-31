# 200 cells instead of six: the first comparison this project could actually resolve

Date: 2026-08-31. Instrument: `scripts/evaluate_policy_arena.py`.
Raw result: `reports/arena/arena-200-20260831.json`.

## Why

Every "is this model better" verdict the season has recorded rests on a
six-cell course. Six cells cannot resolve the differences our changes
produce. The same day's six-cell head-to-head put the
advantage-distilled head **+0.652 fill points** ahead of the shipped
champion, on a paired standard deviation of 4.632 — a minimum detectable
effect, at 80% power, of **5.295**. Every number that comparison could
have produced short of a five-point swing was noise.

## The instrument

Eight scenarios × 25 streams = **200 cells**, three arms, 600 episodes,
**0 failures**. Streams come from the arena band (primes ≥ 809), which
is disjoint from the frozen eval variants, the season-1 wave primes and
the Cup pool, and is re-usable because an arena run measures frozen
policies rather than drawing a single-use corpus.

A Cup cell costs about 180 minutes because it runs six horses *and* the
teacher's physical terminal rollouts. Comparing two frozen policy heads
needs neither, and one episode averages 28 seconds. That is the whole
trick: the expensive thing was never the measurement, it was the
teacher riding along inside it.

## Result

| arm | mean fill | mean placed |
|---|---|---|
| champion (preference, incumbent floor) | **10.370** | 10.83 |
| champion re-deployed as plain argmax | 10.262 | 10.77 |
| advantage-distilled | 10.320 | **11.04** |

Paired against the champion over all 200 cells:

| arm | mean difference | 95% CI | sd | t | W–L–T | sign p | MDE |
|---|---|---|---|---|---|---|---|
| champ-argmax | −0.107 | [−0.242, −0.000] | 0.885 | −1.71 | 16–19–**165** | 0.74 | 0.175 |
| advantage | −0.050 | **[−0.305, +0.213]** | 1.896 | −0.37 | 66–80–54 | 0.28 | 0.375 |

**The advantage-distilled head and the shipped champion are the same
policy, to within ±0.31 fill points.** That is a real null — a bounded
statement — where the six-cell version was merely an absence of
evidence.

## What six cells did to the answer

| | estimate | MDE at that n |
|---|---|---|
| 6 cells | **+0.652** | 5.295 |
| 200 cells | **−0.050** | 0.375 |

The six-cell run got the **sign wrong** and overstated the magnitude by
thirteen times. It also overstated the spread: paired sd 4.632 against
the true 1.896, because six cells happened to include two extremes. Both
errors point the same way — a small course does not merely fail to
detect an effect, it invents one.

This is the finding to carry forward. It applies to every past cup
verdict expressed as a fill difference.

## Two things worth keeping

**The incumbent floor barely exists.** The champion and its own weights
re-deployed as a plain argmax are bit-identical on **165 of 200 cells**:
the "keep provider rank-0 unless clearly beaten" rule almost never
binds. Where it does it is worth at most a quarter of a fill point, and
the sign test (p = 0.74) does not even confirm the direction. The
3.3-point swing it appeared to be worth on `dual-empty` earlier today
was one cell.

**The advantage head places more and fills the same** — 11.04 items
against 10.83, for equal volume. It prefers more, smaller items. Nothing
in the training signal asked for that, and it is the one behavioural
difference between the two heads that 200 cells does resolve.

Per scenario, nothing survives its own confidence interval:

| scenario | advantage − champion | 95% CI | W–L–T |
|---|---|---|---|
| dual-empty | +0.429 | [−0.141, +1.025] | 13–7–5 |
| single-empty-noshelf | +0.134 | [−1.002, +1.332] | 8–7–10 |
| single-preloaded | +0.126 | [−0.419, +0.684] | 8–6–11 |
| dual-preloaded-dedicated | −0.090 | [−0.616, +0.480] | 9–13–3 |
| dual-dedicated-priority | −0.136 | [−0.679, +0.469] | 7–13–5 |
| dual-full-stream | −0.263 | [−0.972, +0.552] | 7–13–5 |
| single-empty-shelf | −0.291 | [−1.151, +0.648] | 4–11–10 |
| dual-shelf-mixed | −0.309 | [−0.905, +0.236] | 10–10–5 |

25 cells per scenario is not enough for a per-scenario claim, which the
intervals say plainly. `--streams` raises it and the run resumes.

## What this changes about how to work

A change is now cheap to *evaluate* and still expensive to *invent*. The
arena costs about an hour for a bounded verdict, so the question
"did that help?" no longer needs a cup, and no longer needs to be
answered by a number that a six-cell course made up.

The corollary is less comfortable: two genuinely different training
signals — nine cups of strict-dominance distillation, and one afternoon
of advantage-weighted regression on 7.5× the rows — land in the same
place, and now we know that to ±0.3 rather than merely failing to tell
them apart. Whatever is limiting this agent, it is not which of those
two losses is used.

## Reproduction

    python scripts/evaluate_policy_arena.py \
      --arm champ=reports/cup/model \
      --arm awr=reports/value/advantage-policy-v1 \
      --streams 25 --workers 4 \
      --work-dir <work> --report <work>/arena-200.json
