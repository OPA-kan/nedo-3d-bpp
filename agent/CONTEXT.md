# Agent context

## 役割

`agent/agent.py`は提出コードの正本で、公開入口は次の3メソッド。

- `get_init_states(init_states)`: コンテナ形状・棚・lookaheadを初期化
- `optimize(item_list)`: Task1の積付順序を返す
- `policy(observation)`: Task2の逐次配置行動を返す

## 固定契約

- 配置候補はコンテナローカル座標、観測済み荷物は世界座標。
- local/world変換はX軸のコンテナoffsetだけ。
- 棚寸法はsimulatorの生成式から導出する。
- 境界は16 mm、搬入経路と側面は16 mmを内部安全量として使う。
- 支持面との垂直接触には搬入クリアランスを要求しない。
- 配置後の観測姿勢から既配置荷物のAABBを再構成する。
- soft/priority荷物を後続荷物の支持面にしない。

詳細は `docs/GEOMETRY_RULES.md` が正本。

## 探索

- 構築順序を共通配置コアでdry-runする。
- Or-opt、swap、2個の逐次再生可能部分列テンプレートを併用する。
- 評価は配置失敗を最優先し、その後に充填・支持・重心を比較する。
- 単品近傍はマクロ近傍で置き換えない。
- オンラインlookaheadは `LOOKAHEAD_SELECTION_MODE` で切替可能。
  `weighted` は既定互換、`depth2` は次手可行性を辞書式優先、
  `pool_resilience` は次に配置可能な可視荷物数を最優先する。
  詳細は `python scripts/context.py show preview-value`。
- コンテナ半空間から姿勢・`(x,y)`ごとの`Zmin/Zmax`を解析的にキャッシュし、
  水平支持候補が全滅した姿勢には低高度の`release_candidate`を生成する。
  release候補は投下点で支持率を要求せず、包含・静的干渉・搬入を通した後、
  PyBullet settle結果を真値とする。
- `RELEASE_RISK_GATE_MODE=off|shadow|enforce`で、releaseのsettled proxyから
  support、CoM margin、overhang、正規化drop、左右/前後support imbalance、
  initial poseを計算する。`shadow`は棄却予定だけを記録し、`enforce`は
  ranking前に閾値外候補を除く。通過候補の`Ranker.score`は変更しない。
  online特徴はcommand/predicted-contact由来だけで、settle telemetryはofflineで
  結合する。traceはstatic/pass/reject/all-rejected/protocol-fallbackを分離し、
  off/shadowのaction command列hash不一致を実験ブロッカーとして集計する。
- 候補生成はdeadline-awareなlazy streamとし、戦略順の荷物、底面積の大きい姿勢、
  残余体積の大きいコンテナから優先する。各三組を64 anchorずつ浅く一巡後、
  256 anchor単位で深掘りし、時間切れ時も最良の検証済みincumbentを返す。
- settled列挙の末尾まで到達しないとrelease候補が出ない退行を避けるため、
  各三組をsettled/releaseの独立unitに分け、同じ浅い一巡で両方を探索する。
- settled候補は、同高かつ辺方向の隙間16 mm以下の支持面を連結成分にまとめ、
  面ごとの局所anchorをpriority round-robinで列挙する。順序は床、大面積、
  奥側、低い上面。連結面の支持率は矩形union面積で評価し、跨ぎ支持を含む。
- `ANCHOR_GENERATOR_MODE=cartesian` で旧直積列挙へ戻せる。offline oracleは
  常に旧Cartesianを明示指定し、anchor recallとbest-score regretの基準を
  新generatorから独立に保つ。
- anchor generatorは`stride`/`stride_offset`でdedup後のanchor列を系統抽出できる。
  Cartesianだけでなく既定の`support_plane`とrelease planeも対応し、
  `iter_attempts` → `iter_prioritized_candidates` → `bounded_rollout_decision`
  → `visible_pool_rollout_value`まで貫通する。skipはyieldせずround枠も消費しない
  ので、**同じattempt予算のまま**grid全体へ到達幅を広げる測定ができる。
  既定は全層`stride=1`（挙動不変）。rollout側の既定は
  `VISIBLE_POOL_ROLLOUT_STRIDE`（既定1）で、evaluation recordに使用strideを残す。
- **`interleave`は`stride`と別物であり、混同してはならない。** `stride`は
  anchorを*間引く*。`interleave`は*並べ替える*（置換）だけで1本も落とさない。
  使い分けはcapの種類で決まる: rolloutのfuture探索はattempt数capで枯渇し得ない
  ので間引きが純増。live探索はdeadline capで**枯渇し得る**ため、間引くと
  現行が見つけている候補を失う。したがってlive経路には`interleave`を使う。
  `support_plane_anchor_positions`は`y降順→|x|昇順`で出すので自然なprefixは
  「奥側の1帯・中心線寄り」になり、これが観測されたlive coverage holeの形である。
  `interleave=N`にすると打ち切られた探索でも支持面全体を粗く走査する。
  適用先は`PlacementCore.choose`と`top_candidates`のみ。`LIVE_SEARCH_INTERLEAVE`
  既定1（出荷順）。cartesian generatorは直積streamで置換を表現できないため、
  `interleave>1`では黙って出荷順を走らせず`ValueError`にする。
- `candidate_diagnostics.support_plane_searches` は姿勢・コンテナごとに
  連結前後のanchor数、面数、成分数、閾値、面優先順の根拠値を保存する。

### オフライン順序探索（Task Aのみ）

- `Agent.optimize` と `DryRunEvaluator` だけがオフライン予算定数を読む。
  公式ハーネスは `agent.optimize` が真のときしか `optimize` を呼ばないため、
  Task B/Cはこの節の影響を受けない。範囲は
  `test_offline_budget_never_reaches_the_online_policy` で固定してある。
- 既定は `OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM=128`,
  `OFFLINE_PAIR_MACRO_BUDGET_SECONDS=0.5`（ADR-002, run 30717998654で採用）。
  1荷物あたりの走査と2荷物マクロ生成の**両方**を有限にしないと、配置不能な
  1荷物が150秒予算を食い尽くし、順序探索そのものが始まらない。
- `OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM=0` と
  `OFFLINE_PAIR_MACRO_BUDGET_SECONDS=0.0` が旧挙動を復元する。
- ドライランのproxyは順序どうしの**相対選択器**であり、配置数の予測値では
  ない。採用runではproxy 23に対し物理25で、armによって誤差の符号が変わる。
- 採用値は内部予算150秒のうち147.3秒を使う。配置コアを遅くする変更は、
  Task Bベンチマークではなくここに最初に現れる。

## 現在の状態

- 回帰テストは `python scripts/run_checks.py` で一括実行する。
- GitHub Actions上でCPUシミュレータを再現可能。
- run 30331700531では各ケース7個配置後に失敗し、LD3斜面を水平支持面として
  表現できないことが主要な偽陰性と判明した。
- release候補実装後のrun 30334277618ではCase 000/001とも13個まで配置した
  （旧runは各7個、合計14→26）。release後の変位は概ね鉛直52 mm、
  姿勢変化は0〜0.1度で、斜面での顕著な滑り・傾きは観測されなかった。
- 両ケースともstep 13で終了した。Case 000は8秒のpolicy timeout後に
  simulatorのrandom fallbackが失敗、Case 001は候補を受理できず固定fallbackが失敗した。
  次の共通ボトルネックは直積アンカー列挙の時間と後半のstatic/support/corridor棄却。
- run 30337216417では最大policy時間が9.87秒から6.52秒へ下がり外部timeoutを
  解消した一方、release候補がsettled全列挙の末尾に隠れてCase 000/001が
  12/7個へ退行した。release独立unit修正後の物理結果は未検証。
- 診断には探索unitの開始数/総数、round数、deadline到達、incumbent更新数を保存する。
- `NEDO_POLICY_TRACE_PATH`有効時は、可視poolの各荷物についてitem cap、探索開始、
  候補生成、immediate top-K、future probe、選択の各stepを累積保存する。
  `candidate_generated`はdeadline内で観測した候補でありoracle可行性ではない。
  trace無効時は荷物別lifecycleを収集せず、選択方策も変更しない。
- `CROSS_STEP_INCUMBENT_MODE=shadow`は通常探索で合格した候補をstable item index
  ごとに保持し、次stepでpool再対応付けと完全な静的可行性再検証を行う。
  返却actionには使わず、`would_prevent_protocol_fallback`、生存数、棄却理由、
  再検証時間だけをtraceする。既定は`off`で、`enforce`は未実装。
  詳細は`docs/CROSS_STEP_INCUMBENT.md`。
- `TEMPORAL_CHUNK_ENSEMBLE_MODE=shadow`は、現在選択を起点とする固定予算の
  静的rolloutから将来offset別の行動提案を保存する。対象stepでstable item IDを
  現poolへ再対応付けし、完全な静的契約を通した後、複数origin stepの提案を
  `(item, container, orientation, kind, coarse x/y)`で集約する。live actionは
  変更せず、delay別生存率、最大票、現選択との一致、fallback救済可能性、計算税を
  traceする。既定`off`、`enforce`未実装。詳細は
  `docs/TEMPORAL_CHUNK_ENSEMBLE.md`。
- `VISIBLE_POOL_ROLLOUT_MODE=shadow`はlive actionを変えず、探索中に受理済みの
  候補をitemごとに1件保持し、寸法・質量・soft/priority属性の同値classを
  多様化したTop-Kだけに固定attempt数の静的rolloutを行う。値は
  `(future settled配置数, 追加体積, -累積回転risk, -累積slide risk)`。
  初手releaseはsettled proxy利用を明記し、rollout途中のreleaseは適用せず
  `release_transition_uncertain`で打ち切る。既定`off`。`enforce`は
  `Q_live >= Q_selected - 0.15`の候補間だけrollout辞書式値で選び替える
  ablation modeであり、採用済み既定ではない。
  詳細は`docs/VISIBLE_POOL_ROLLOUT.md`。
- `ITEM_COVERAGE_MODE=class_aware`では、normal/soft/priorityの各present classから
  最低1荷物をitem cap内へ確保し、各included itemの先頭探索unitを残りposeより先に
  一巡する。`legacy`で従来prefixへ戻せる。配置ranking scoreは変更しない。
- policy traceは全体・class別に
  `included/visible`、`search_started/included`、
  `candidate_generated/search_started`を記録する。
- 3方式は引き続き同一履歴であり、30個前後へ届くまでlookahead比較・重み調整は保留する。

## Structured placement pipeline

- Candidate search emits `PlacementProposal`; it no longer needs to hide item,
  container, orientation and provenance behind the final action dictionary.
- `Ranker.evaluate()` retains the seven immediate score components, while
  `release_risk_adjustment()` retains rotation/slide probabilities and
  penalties.  `PlacementDecision.score` remains the compatibility scalar.
- `PlacementCore.choose()` and `top_candidates()` accept an optional selector.
  Their defaults (`SettledFirstSelector` and `TopKSettledFirstSelector`)
  preserve the shipped settled-before-release behavior exactly.
- Rich proposal/evaluation objects are opt-in through a custom selector or
  `structured_evaluation=True`; the default live path retains the old scalar
  allocation profile. Eager materialization reduced measured candidate
  throughput by about 16--17% and is not permitted as a default tax.
- `PlacementCommand` is the simulator command pose, not a predicted settle
  pose. `action_for_execution()` owns conversion to the external action API.
- A selected structured evaluation is written to policy diagnostics under
  `selected_candidate_evaluation`. Advanced selectors should consume that
  evaluated stream rather than rerun search to reconstruct terms.
- `PLACEMENT_SELECTOR_MODE=structured_noop` routes the shipped score and
  settled-first rule through the rich path. It is a physical negative control,
  not a new ranking policy; its full-vector protocol is in
  `docs/STRUCTURED_SELECTOR_EXPERIMENT.md`.
- `structured_retained` leaves candidate scanning scalar and enriches only
  the retained decision/Top-K. `MULTI_AXIS_SELECTOR_MODE=shadow` consumes that
  portfolio once, records separate rule, risk, support and predicted-CoM axes,
  and proposes a Pareto-front candidate without changing the executed action.
  CoM is telemetry-only until its official direction is resolved; no local
  weighted total is constructed. See `docs/MULTI_AXIS_SELECTOR.md`.
- `RESIDUAL_AFFORDANCE_SHADOW_MODE=shadow|guarded_enforce` scores the frozen retained Top-K
  with the exact action-only ridge confirmed on runs `32372290412` and
  `32375696343`. It runs only after the ordinary live decision is frozen.
  `shadow` records without changing it; the development-only
  `guarded_enforce` canary executes only the conservative proposal. The trace
  records both the unrestricted proposal and a
  guarded proposal that may not increase direct or stack-aware soft/priority
  coverage or priority-routing violations. See
  `reports/counterfactual-afterstate-value/residual-affordance-shadow-protocol.md`.
- Corrected live run `32381957502` observed 280 decisions and 835 candidates:
  unrestricted/guarded proposals changed 123/120 actions, and the guard
  blocked all five proposals that worsened a soft/priority contract axis.
  The preregistered physical negative control nevertheless failed at 2/15
  matching action hashes, so this remains telemetry-only and no enforce
  canary is licensed.
- Negative-control v2 records selected-action and retained-portfolio
  immutability inside the same policy call, then evaluates physical variation
  separately against simultaneous base repeats. Independent action hashes are
  retained as diagnostics only. See
  `reports/counterfactual-afterstate-value/residual-affordance-shadow-negative-control-v2.md`.
- V2 run `32435231411` passed same-call invariance (287/287), reach (126
  guarded changes), and attribute safety (all 6 regressions blocked), but
  failed 23/65 physical comparisons because same-wave base spread was often
  exactly zero. V3 is frozen prospectively against base-only calibration from
  runs `32380902237`, `32381957502`, and `32435231411`; calibration shadow
  values are excluded. It also invalidates a current base outside that domain.
  See `reports/counterfactual-afterstate-value/residual-affordance-shadow-negative-control-v3.md`.
- Prospective v3 run `32436768825` passed the frozen gate: 284/284 incumbent
  and portfolio decisions unchanged, 135 guarded proposals across 27 items,
  and all 65 physical comparisons inside the fixed base-only calibration
  (zero baseline/effect breaches or missing metrics). Its compact evidence is
  under `reports/residual-affordance-shadow/history/32436768825/`. This
  licenses a separately preregistered guarded-enforce development canary, not
  an official submission or a score-improvement claim.
- Guarded-enforce canary v1 is preregistered in
  `reports/counterfactual-afterstate-value/residual-affordance-guarded-enforce-canary-v1.md`.
  Its gates do not form a weighted total: executed reach, placed/fill/steps,
  soft/priority, five shake axes, and three terminal axes must pass
  independently. A development PASS licenses unseen-case replication only.
- Canary run `32438901241` validly failed after 101 actions were enforced:
  placed -2.333, fill -3.429, steps -2.333, and shake peak KE +47.899. The
  attribute and terminal gates passed, confirming that the guard worked but
  the value target did not. Only 2/101 enforced actions preserved immediate
  score. Reject global enforcement of `action-ridge-32351615182-v1`; the next
  model must learn candidate-conditioned trajectory advantage including both
  immediate cost and suffix outcome. See
  `reports/counterfactual-afterstate-value/residual-affordance-guarded-enforce-canary-v1-result.md`.
- This is an integration contract, not a new adopted ranking policy.  See
  `docs/PLACEMENT_PIPELINE.md`.

## Release fallback ordering

- Settled and release candidates are searched as independent units so that a
  release probe cannot be hidden behind exhaustive settled-anchor enumeration.
- Their incumbents are kept separately. If any validated settled candidate
  exists, it is chosen regardless of the release candidate's heuristic score.
- A release candidate is returned only when the search found no settled
  candidate.
- 候補が尽きた内部状態は`no_safe_action`、外部APIへ残している固定座標は
  `unsafe_protocol_fallback`としてtraceする。状態依存fallback生成器
  \(F(s,i,d)\) は未実装で、固定座標を安全なfallbackとは扱わない。
- cross-step incumbentは上記固定fallbackをまだ置換しない。shadowで次step
  生存率と再検証税を測ってから、別アブレーションで返却契約を検討する。
- run 30707120494では一般stepの静的生存率は702/1,603 (43.8%)だったが、
  唯一のprotocol fallback stepでは18件全てが再検証落ちとなった
  (`corridor` 17、`static_geometry` 1)。`would_prevent=0`のため、現行top2
  持越しをfallbackとして使う案は棄却し、既定`off`を維持する。
- Run 30340049061 confirmed that this ordering is not sufficient on its own.
  Case 000 improved to 15 placements, but Case 001 still had no settled
  candidate at step 4 and its release fallback failed after settling by
  0.638 m with a 90-degree rotation. Release candidates therefore need an
  additional stability/risk gate; heuristic ordering was not the root cause.
- `scripts/measure_anchor_recall.py` is an offline-only oracle. It snapshots
  every requested pre-action state, audits the settled candidates actually
  found before the policy deadline, enumerates the legacy Cartesian set
  without a deadline, and validates each oracle candidate with isolated
  PyBullet settle trials. See `docs/ANCHOR_RECALL_ORACLE.md`.
- release oracleは同じ候補についてgateのpass/reasonsと物理結果を突き合わせ、
  30度超回転・底面短辺の0.5倍超変位・physical invalidを危険ラベルとして
  TPR/FPRを保存する。
- Run 30348998307の保存snapshotへper-support-plane版を再生すると、step 3の
  deadline内settled発見数は0から349、step 4は0から427へ増えた。step 4の
  選択は旧oracle最良候補と一致した。全列挙比較ではstep 4の試行を
  116,008から10,438へ91.0%削減し、旧最良scoreを保持した。新trajectoryの
  PyBullet物理結果は未確認。
- failure-step oracleはCartesian/support-plane settledのunionとreleaseを
  別々に物理検証する。policyはaccepted settled/release、action source、
  deadline、unit進捗、incumbent更新数を保存し、固定fallbackを
  deadline miss / safe release only / oracle集合内dead end /
  incumbent invariant violationへ分類する。対象はCase 000 step 13/14と
  Case 001 step 9/10で、compact結果をrun historyへ残す。
- run 30364892792のfailure snapshotではCase 000 step 14/Case 001 step 10の
  settledは0件だったが、物理安全releaseが460/1,014件存在した。releaseを
  Cartesian直積からsupport-plane局所`(x,y)`と解析的`Zmin/Zmax`の直接生成へ
  変えた非物理replayでは、最初の候補が2,763→45試行、804→10試行となり、
  両stepとも固定fallbackではなく0.12秒以内にrelease候補へ到達した。
  選択候補のPyBullet settleと新trajectoryは未確認。
