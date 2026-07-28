# Preview-aware residual value context

## 目的

オンライン配置を「現在荷物を置いた後、可視poolと未知未来に対して
どれだけ有用な状態を残すか」で評価する。

これは既存のマクロ・EP/EMS・DPOR理論を置き換えない。既存理論は探索空間を
圧縮する機構、このprofileは圧縮後の候補を比較する評価原理である。

## 状態

残余空間やheightmapだけを完全状態とはしない。物理状態にはsettle後姿勢、
支持可能性、搬入経路、荷物属性、コンテナ制約が必要である。

## pool別の扱い

- オフライン順序あり・pool 1: 計画済みの次荷物を固定previewとして使える。
- pool 2以上: 次荷物も選択対象なので、残った可視荷物全体を評価する。
- 順序なし・pool 1: previewは存在せず、未知荷物分布に対する解析値が必要。

## 状態

- `weighted`: Implemented / 既定互換baseline。
- `depth2`: Implemented。次手可行性、次手score、即時scoreを辞書式比較。
- `pool_resilience`: Implemented proxy。次に配置可能な可視荷物数を最優先。
- 連続的な可行アンカー面積、期待可行面積、sibling ranking: Proposed。
- Gated Iota: Out of scope。

## 最新診断（run 30331700531）

- 3方式は両ケースとも7個で停止し、方式比較を始められる段階ではない。
- 空コンテナの扉側・中央・奥への搬入テストはすべて通り、Y回廊反転は棄却した。
- 失敗stepの `corridor` 棄却はCase 000で0、Case 001でも38 / 120,288試行で、
  支配原因ではない。
- 深さ中心はCase 000で-0.028、Case 001で+0.214。前後占有もそれぞれ
  0.132/0.142、0.060/0.118で、front-blocking仮説を支持しない。
- 高いCoGは最初から棚面 `z≈1.0 m` へ置いた履歴で説明できる。
- 固定fallbackが成功するstepでも通常候補は0。実LD3面で再計算すると、
  水平床上の中央候補は斜め下部境界への食込みでcontainment棄却される一方、
  `z=0.25 m` の空中actionは包含を通り、PyBulletで斜面へsettleする。

したがって主要な偽陰性は、共有配置コアがLD3の斜面支持・低高度dropを候補として
表現していないことにある。次は固定fallbackの座標調整ではなく、斜面上の包含下限から
安全なdrop action候補を作り、PyBullet settle後に再評価する。

## 投下候補（Implemented / physics validated）

- コンテナ半空間から姿勢・`(x,y)`ごとの`Zmin/Zmax`を解析的に計算しキャッシュする。
- 区間外候補は詳細判定前に`envelope_pruned`とし、構造的なcontainment試行を除く。
- 水平支持候補がない姿勢だけ、footprint最大高さより52 mm上の
  `release_candidate`を追加する。
- release候補は投下点で支持率を要求しない。包含、静的干渉、搬入経路は維持する。
- offline/lookaheadでは包含下限と支持高さによるsettled proxyを使うが、
  斜面上の傾きは次の実観測まで未知として扱う。
- settle後の位置変位、角度差、最終quaternion、AABB寸法をstep履歴へ保存する。

run 30334277618のsample_configでは、Case 000/001とも配置数が7個から13個へ増えた。
release候補のsettle変位は概ね鉛直52 mm、姿勢変化は0〜0.1度であり、現時点では
斜面領域を占有ボクセルへ切り替える根拠となる滑り・傾きはない。一方、両ケースとも
step 13で停止した。Case 000は候補探索が8秒timeoutに達した後のrandom fallback、
Case 001は候補全滅後の固定fallbackによる失敗である。したがって次の実験単位は
lookahead価値関数ではなく、候補生成の直積列挙削減と時間内に確実な候補を返す探索契約。
30個前後へ到達するまで3方式の優劣比較は保留する。

## Anytime候補探索（Implemented / physics validation pending）

- 候補生成をlazy stream化し、anchor試行ごとにdeadlineを監視する。
- 戦略順の荷物、底面積の大きい姿勢、残余体積の大きいコンテナで三組を順位付けする。
- 各三組を浅く一巡して探索飢餓を防ぎ、その後に優先順のまま深掘りする。
- settled候補とrelease候補を独立unitにし、通常候補の全列挙を待たず
  同じ第1巡で低高度投下候補も検証する。
- 幾何・支持・搬入を通った候補のうち最良scoreをincumbentとして更新し、
  deadline時には固定座標ではなく検証済みincumbentを返す。
- anchor集合自体は旧Cartesian列挙を維持する。支持面ローカル化と跨ぎ支持の
  recall/regret/配置数差は次の独立実験とする。

完全な定式化、限界、実験計画は `PREVIEW_RESIDUAL_VALUE.md` を読む。

## Release fallback ordering

The anytime search maintains separate settled and release incumbents. A
validated settled candidate has lexicographic priority over every release
candidate; release is used only if no settled candidate was found before the
deadline. This prevents the heuristic value function from trading away
physical certainty for a nominally higher release score.

Run 30340049061 showed that the ordering is useful but insufficient. Case 000
improved to 15 placements. Case 001 still had no settled candidate at step 4,
so release was correctly used as the fallback and then failed after 0.638 m of
settle displacement and a 90-degree rotation. Thus a high release score
overriding a settled candidate was not the root cause. The next required
mechanism is a release stability/risk gate or a safer fallback candidate, not
another value-function weight change.

## Anchor recall oracle

Before replacing the Cartesian anchor set, run the offline oracle documented
in `docs/ANCHOR_RECALL_ORACLE.md`. It compares the settled candidates found by
the actual deadline-bound policy with an unlimited enumeration at the exact
same pre-action state. Physical recall uses isolated PyBullet settle trials as
the denominator. Per-support-plane generation is justified when the oracle
finds safe settled candidates that the anytime search misses.

The implemented generator groups coplanar edge-adjacent support surfaces with
a 16 mm horizontal threshold, computes bridge support from rectangle-union
area, and searches components in a priority round-robin: floor, larger area,
greater depth, then lower height. The legacy Cartesian generator remains an
explicit oracle mode. On the run 30348998307 snapshots, step-4 settled trials
fell from 116,008 to 10,438 while preserving the legacy oracle's best score;
deadline-bound settled discoveries rose from zero to 427. Physical trajectory
validation remains pending.
