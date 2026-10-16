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
