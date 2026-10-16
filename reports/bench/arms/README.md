# Bench arm specs

One line per file, the arm spec `python -m bench run` and the `bench-run.yml`
workflow take (`arm` input).

- `arm_ship_c.txt`, `arm_ship_b.txt`: **the shipped v50 form** on Tasks C and
  B, field for field (checked by building `submission/agent.py`'s
  `OVERRIDES` config and diffing it against `bench.arms.make_arm(spec).config`:
  only the Task A planner fields differ). Use these as the baseline arms;
  the records are `reports/bench/ship-core`, `ship-core-b`, `ship-hard2`,
  `ship-hard2-b`.
- `arm_gate0_c.txt`, `arm_gate0_b.txt`: the v50 arms the `gate0-*` records
  were run with. They differ from the shipped form in `stack_deadline`
  (off), `rescue_order_gate` (`low`, so Task B ran the deep-first / sealing
  pass the shipped `low+single` keeps to C) and `soft_headroom_volume_share`
  (0.75 against 0.9); on C also `grid_rescue_pool_seconds` (no effect with a
  pool of one). Kept for reading the older records.

To measure a change, append `,field=value` to the ship arm's line.
- `arm_ship_a.txt`: the shipped v50 form on Task A (`OVERRIDES` plus the
  `task_a` overrides `submission/agent.py` applies in `optimize`), field for
  field (only the plan-score weights string differs, in form not value).
  Baselines: `reports/bench/ship-core-a`, `ship-hard-a`, `ship-dense-a`.
- `arm_acount_a.txt` / `arm_acount0_a.txt`: the shipped A arm with the
  count-secured re-plan (`plan_count_secure`) under the threshold plus 2 /
  under the threshold itself (`reports/wedge/a-count-secure.md`). Records:
  `reports/bench/acount-*`, `acount0-*`.
- `arm_astand_a.txt`: the shipped A arm with the typed-standing plans under
  the count gate (`plan_typed_standing`, `reports/wedge/a-standing.md`);
  records `reports/bench/astand-*`. `arm_astandf_back_a.txt` /
  `arm_astandf_front_a.txt`: the gallery forced on every manifest, braced
  (against the back wall, the hard rows in front) and at the opening
  (braced on one side), for the stability cost; records `astandf*-*`.
  `arm_astand2_a.txt`: the braced variants only; `arm_astand3_a.txt`: the
  same, kept off layouts with a priority container (the candidate form);
  records `astand2-*`, `astand3-*` (dense-a has no priority container, so
  `astand2-dense-a` stands for both).
- `arm_acs_a.txt`: the v51 A form (`arm_acount0_a`) plus the typed-standing
  gallery (`plan_typed_standing`, braced variants, no priority container),
  the combination measured as `reports/bench/acs-*`.
- `arm_adry_a.txt` / `arm_aplan_a.txt`: the shipped A form with the ladder's
  dry-run alone (`offline_planner=` empty) / the row planner alone
  (`offline_dry_run=false`); records `reports/bench/adry-*`, `aplan-*`.
- `arm_atail_a.txt` / `arm_atailp_a.txt` / `arm_atails_a.txt`: the shipped A
  form with the order's tail after the plan rearranged
  (`plan_tail_order=soft-first` / `soft-first-prio-last` / `small-first`,
  reports/wedge/a-tail-order.md); records `reports/bench/atail*-*`.

- `arm_softl-{base,col,pg,sos,colsos,all}_{c,b}.txt`: the soft-ladder round
  (`reports/wedge/soft-ladder.md`) on the shipped C and B arms: `base` is
  the ship arm again (the replicate spread); `col` the typed-column rung
  (`soft_tops_for_soft`); `pg` the four pocket-guard fixes
  (`pocket_guard_deadline_share=0.5`, `_all_rooms`, `_tie_soft_top`,
  `_phase_prior`); `sos` the shadow's soft-on-soft thresholds and pre-settle
  (`shadow_soft_on_soft_drift_xy=0.08`, `_angle_deg=12`,
  `shadow_presettle_steps=60`); `colsos` the column rung with the shadow
  fields; `all` every field and `priority_tops_for_priority`. Records
  `reports/bench/softl-<arm>-core` (C) and `softl-<arm>-core-b` (B), priced
  against `ship-core` / `ship-core-b`; `softl-col-hard2` and
  `softl-all-hard2` against `ship-hard2`. None shipped.

- `arm_ps03_{c,b}.txt`, `arm_ps04_{c,b}.txt`: the shipped C and B forms with
  the phase switch at a usable surface of 0.3 / 0.4
  (`phase_switch_surface`); records `reports/bench/ps03-*`, `ps04-*`
  (findings, "The usable surface falls in cliffs").
- `arm_cliff_{c,b}.txt`: the shipped C and B forms plus the cliff veto
  (`cliff_veto=true`: in the middle band of the phase, usable surface 0.25
  to 0.6, a rung's pick that closes more than 0.12 of the floor beyond its
  footprint yields to the first survivor of its rung that closes less than
  half of it; `reports/wedge/cliff-veto.md`). `arm_cliff08_{c,b}.txt`: the
  same at `cliff_veto_close=0.08`. Records `reports/bench/cliff-sample-c`,
  `cliff-sample-b`, `cliff-core`, `cliff-core-b` and `cliff08-*`, priced
  against `ship-sample-c`, `ship-sample-b`, `ship-core`, `ship-core-b`.
- `arm_pair_b.txt`: the shipped B form with the same-class pair
  reservation (`pair_reserve`: a narrow-topped floor box laid where its
  partner in the pool fits flush beside it, the partner placed there on
  the next call; `reports/wedge/pair-reserve.md`).  Records
  `reports/bench/pair-sample-b`, `pair-core-b`, `pair-hard2-b`, priced
  against `ship-sample-b` / `ship-core-b` / `ship-hard2-b`; the
  `pair0-*` records are the first form, whose spot skipped the ladder's
  vetoes and went into the priority strip.
- `arm_sfr_b.txt`: the shipped B form plus the restricted soft-first pass
  (`soft_first_restricted`: before the hard cargo, each soft item in the
  pool, smallest first, goes first when the ladder's pose for it rests on
  soft cargo or on a hard top no hard or priority item of the pool could
  stand on -- never a shelf, never the floor; 30 % of the budget;
  `reports/wedge/soft-first-restricted.md`).  `arm_sfr50_b.txt`: the same
  at `soft_first_restricted_share=0.5`.  `arm_sfrt_b.txt`: the same with
  the tops ask (`soft_first_restricted_tops`: when the ladder's own pick
  is refused, the ladder over item surfaces with the soft-on-soft column,
  then the stack option).  Records `reports/bench/sfr-sample-b`,
  `sfr-core-b`, `sfr-hard2-b`, `sfr50-sample-b`, `sfr50-core-b`,
  `sfrt-sample-b`, `sfrt-core-b`, `sfrt-hard2-b`, priced against
  `ship-sample-b` and against `shipr-core-b` / `shipr-hard2-b`: fresh
  replicates of the shipped B arm run in the same CI window, since the
  `ship-*` records had drifted (+1.2 / +2.0 against them); use the
  `shipr-*` records as the B bases from here.

## Judging a run

`python -m bench.platform_score <base_dir> <new_dir> ...` prices every
episode the way the platform does (the five weights, the count gate, the
calibrated cog and stability, the credited soft and priority shares) and
prints the suite means and the paired difference with a bootstrap interval;
`--mix core-a=9,core-b=11,core=3` weights suites by the platform's task
shares.  This is the objective for every lever from here: a crossing count
or a placed count is a diagnostic, the platform score is the verdict.
- The dry-run's time (`reports/wedge/a-count-secure.md`, section 7):
  `arm_adfirst_a.txt` (`plan_dry_run_first`: the ladder's dry-run before the
  planner on every layout), `arm_adfirstd_a.txt` (on manifests whose volume
  is at least 0.62 of the containers', `plan_dry_run_first_dense=0.62`),
  `arm_adfirsts_a.txt` (on the manifests under that share, `-0.62`). The
  short-budget records append `offline_budget_seconds=20` / `30` to the
  arm: `reports/bench/<form><budget>-<suite>` (`ship20-dense-a`,
  `adry30-hard-a`, `aplan30-core-a`, `adfirsts20-dense-a`, ...), each judged
  against the `ship<budget>-<suite>` record; `adfirst-*`, `adfirstd-*`,
  `adfirsts-*` at 140 s.
