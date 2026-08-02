# ADR-002: オフラインドライランの1荷物あたり作業予算を有限にする

**Status:** Accepted / Implemented
**Date:** 2026-08-02
**Revised:** 2026-08-02 — 決定の中心を「探索量の増加」から「評価写像の固定
仕事量化(マシン速度の除去)」へ書き直した。数値と採用値は変更していない。
**Amends:** ADR-001 §5「局所探索と時間制御」
**See also:** ADR-003（proposal oracle と execution oracle の役割分担）
**Scope:** 課題Aのみ（`agent.optimize` が真のときだけ公式ハーネスが呼ぶ経路）

## Context

ADR-001 §5は探索予算を「180秒制限のうち最大150秒」と定め、「配置コアが遅い
場合は自動的に評価回数が減るため、楽観的な固定反復回数には依存しない」と
書いた。ADR-001の Remaining Work #5 は、その前提を実測することを残していた。

実測した結果、前提は成り立っていなかった。時間制御はグローバル締切だけで
あり、1荷物あたりの上限が無い。ある荷物が配置不能になると、その1荷物の候補
走査が残り予算をすべて消費して締切に到達する。したがって「評価回数が自動的
に減る」のではなく、**順序探索が始まる前に予算が尽きる**。

公式相当の150秒内部予算で計測した既定実装（Actions run `30717998654`,
バンドル済み課題Aケース000, 41荷物, 3反復）:

- 全順序の評価数: 3.0（`OFFLINE_MAX_EVALUATIONS` の既定は1000）
- 物理配置数: 20

1回のドライランに約35秒かかるため、150秒の中に seed + 近傍2件しか入らない。
局所探索は完全に止まっていたわけではなく（近傍1件は採択された）、
1000回の評価枠のうち3回しか使えていなかった。近傍2件はいずれも
placed_count と初回失敗indexを改善せず、`constructive_order` からの改善は
辞書式順序の下位キーにとどまった。

最初のローカル調査は、直列に並んだ2つの予算食いを分離した。5秒予算では、
legacy評価はseedしか試せなかった。1荷物64試行で境界を付けるとseed評価は
1.82秒で終わったが、今度はpair-macro生成が残り3.18秒を消費した。**両方の
段を有限にしなければ順序探索は始まらない。**

## Decision

**本質は探索量ではなく、評価写像の固定仕事量化である。**

初版は本 ADR を「1荷物あたり128候補まで探索量を増やした」と説明した。それは
浅い。実際に起きたのは評価写像そのものの性質変化であり、

    E_{theta,m}(pi)  -->  E_{theta,128}(pi)

すなわち**内側評価からマシン速度 m をほぼ除いた**ことである。

fixed-attempt enumeration によって、offline order evaluation を壁時計依存の
anytime policy から分離した。グローバル締切付近の末尾評価は打ち切られ得るが、
確定済みの評価値と incumbent はマシン非依存に保持される。

実測（ケース000）: 遅い箱で55順序、速い箱で79〜80順序と**外側で評価できた
順序数は速度依存**だったにもかかわらず、選ばれた41要素の順序は
**全実行で完全一致**した。すなわち

    E_{theta,128}^{slow}(pi) = E_{theta,128}^{fast}(pi)

が実測されている。対照的に legacy arm（`choose` による deadline 駆動列挙）は
3反復で fill が 27.541〜30.176 とばらつき、順序自体が run ごとに変わる。

この性質は ADR-003 の proposal oracle 要件のうち「マシン非依存性」そのもので
ある。配置数の改善（20 → 25〜26）はその帰結であって、決定の根拠の中心では
ない。

課題Aのオフラインドライランについて、次の2つを既定で有限にする。

1. `OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM = 128`
   各荷物の候補走査を、決定的な幅優先アンカー試行128回で打ち切る。
   `PlacementCore.rescue_choose` の作業予算機構を再利用する。
2. `OFFLINE_PAIR_MACRO_BUDGET_SECONDS = 0.5`
   2荷物マクロ生成段を、残り予算からではなく独立した0.5秒で打ち切る。

どちらも環境変数で上書きでき、`0` / `0.0` が従来の挙動を復元する
（`OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM=0` はグローバル締切だけの走査、
`OFFLINE_PAIR_MACRO_BUDGET_SECONDS=0.0` は残り予算方式のマクロ段）。

ADR-001 §5の他の要素（150秒予算、移動平均による次評価判定、最大1000評価、
固定シード、best-so-far フォールバック）は変更しない。この決定は §5に
**1荷物あたりの上限**を追加するものであり、置き換えではない。

### 128を選ぶ理由

64は棄却された。run `30717533328` で64は構造的な移植には成功し、評価数を
1から58（source 000）/ 102（source 001）へ増やしたが、実行可能なprefixを
過小評価した。物理配置数は 20.0 → 19.33（source 000）で、両ソースとも
fillが下がった。順序を多く見ても、各順序の評価が浅すぎて選別が壊れる。

128は run `30717848749`（30秒予算）と `30717998654`（150秒予算）の両方で
正だった。評価数と1評価あたりの深さの積が予算に収まる領域にある。

## Consequences

公式相当時間枠・Linux/PyBullet・3反復（run `30717998654`, ケース000）:

| arm | 物理配置数 | fill | 全順序評価数 | optimization 秒 |
|---|---:|---:|---:|---:|
| base（legacy） | 20 / 20 / 20 | 29.298 | 3.0 | 112.1 |
| 採用値（bounded128） | 25 / 25 / 25 | 34.949 | 51.3 | 147.3 |

**この表は run 30717998654 単独の値である。** 後続の run 30721071243 では
採用arm が placed 25.333 [25, 26] / fill 35.615 を返した。物理結果は定数では
なくレンジ（25〜26 配置、fill 34.949〜36.946）であり、差はマシン速度に由来
する。**オフラインが選ぶ順序は全実行で同一**で、変動はオンライン実行側にある
（`task-a-episode-outcome-is-machine-speed-dependent`）。

- 配置数 +25%、fill +19.3%
- 重心高さ 約0.753 → 0.735 m（低いほど良い）
- near-miss は両方式とも0
- 採用側は**選ばれる順序**が全実行で一致する。物理結果は run 30717998654 と
  30719944050 では 25 で一定だったが、30721071243 で 25〜26 に振れた。
  「物理結果も完全に一致する」は初版の誤りで、撤回済み
- optimization 147.3秒は150秒の内部予算内、180秒の外部制限内
- policy時間 約6.51秒は維持され、8秒のpolicy制限内

課題B・課題Cへの影響は無い。この2つの定数は `DryRunEvaluator` と
`Agent.optimize` 以外から読まれず、公式ハーネスは `agent.optimize` が真の
場合しか `optimize` を呼ばない。この範囲限定は
`test_offline_budget_never_reaches_the_online_policy` で固定してある。

負の帰結として、探索が実際に動くようになったぶん予算消費が112.1秒から
147.3秒へ増えた。内部150秒に対する余裕は約2.7秒、外部180秒に対する余裕は
約32秒である。配置コアを遅くする変更は、Task Bベンチマークではなくここに
最初に現れる。変更時はこの表を測り直すこと。

## Limits

この決定が主張していないことを明示する。

1. **オフラインproxyは絶対スコアではない。** 採用側のproxyは23個を予測し、
   物理実行は25〜26個だった。proxyは順序どうしの**相対的な選択器**として使う。
   proxy値そのものを目標値や報告値として扱ってはならない。差の原因としては、
   ADR-003 の risk-off proposal と risk-on execution の方策差が**候補の一つ
   として特定されている**が、差の符号や大きさを説明できたわけではない。
2. **fallback問題は未解決である。** 採用後も25個目以降は invalid action で
   エピソードが終わる。この決定は順序探索を動かしただけで、終盤の行動供給を
   直していない。`transport-deaths-are-fallback-poison` を参照。
3. **1ケースの結果である。** run `30717998654` はバンドル済みケース000だけを
   3反復した。source 001 は課題Aへの合成変換であり、採用runからは外した。
   別ケースでの再現は未測定である。
4. **128は最適値ではない。** 64（棄却）と128（採用）の2点しか測っていない。
   256以上、および荷物数に応じた適応予算は未測定である。

## Implementation

- `agent/agent.py`: `OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM`,
  `OFFLINE_PAIR_MACRO_BUDGET_SECONDS` の既定値、`DryRunEvaluator`,
  `Agent.optimize`, `Agent._append_offline_optimization_trace`
- `tests/test_agent.py`: `OfflineOptimizationTests`
  - `test_offline_defaults_ship_the_adopted_bounded_rollout`
  - `test_unconfigured_dry_run_uses_the_shipped_attempt_budget`
  - `test_zero_attempts_restores_the_legacy_unbounded_scan`
  - `test_offline_budget_never_reaches_the_online_policy`
  - `test_optimize_reports_the_shipped_budget_it_actually_used`
  - `test_dry_run_places_simple_sequence_with_common_core`（両予算で実行）
- `scripts/run_task_a_rollout.py`: `configure_task_a_arm` の arm 定義
- `docs/TASK_A_ROLLOUT_TRANSFER.md`: 設計と全run履歴
- `context/evidence.json`: `task-a-bounded128-adopted` ほか
