# Board receptivity: A, R, H

盤面を「今の利得」ではなく「次に何が来ても受け入れられるか」で評価する項。
実装は `agent/agent.py` の board セクション、既定はまだ off
(`LOOKAHEAD_SELECTION_MODE=weighted`)。

## 何を計るか

ランカー(`Ranker.score`)は体積・支持・奥行き・優先ルーティングと
release risk の差引きで、**その手で得るもの**を採点する。**その手が盤面から
奪うもの**に対応する項は一つもない。同じ体積を得る二つの候補が、残す盤面に
おいて全く違うことがありうる。

一流のプレイヤーがやっているのは「穴を作らない」ではなく、**次に何が来ても
壊れにくく、修復可能な盤面を維持する**ことだった。それを三つに分ける。

| 記号 | 名前 | 定義 |
| --- | --- | --- |
| **A** | acceptance breadth | まだ流れている形状のうち、着地点が 1 つ以上残っているものの数 |
| **R** | alternativity | 各形状の着地点の数(上限 `BOARD_SITE_CAP`) |
| **H** | repairability | 表面下に封じた空隙 `sealed_volume` と、表面の粗さ `roughness` |

A と R の区別が要点である。着地点が 1 つの形状は、**到着順の人質**になって
いる。間に別の手が入ればその 1 点は消えるので、「置ける」と「置ける見込みが
ある」は別物になる。R はそこを分ける。

H は A とは時間軸が違う。A は今の受容性、H は**悪い今を後から取り消せるか**。
封じた空隙はどの後続手でも回収できないので、A が同じなら H が判定する。

順序は lexicographic で `(A, R, -sealed_volume, -roughness, incumbent_score)`。
breadth を失うことは tidiness で買い戻せない — 何も受け入れない綺麗な盤面は
終わっている。最後の `incumbent_score` により、board が区別できない候補集合の
中では**出荷時の挙動そのもの**になる。

## 表現

すべて 2.5D の高さマップから読む。テトリスの盤面がまさにそれである。

* 格子はコンテナ内寸を `BOARD_CELL_SIZE`(既定 0.05 m)で割ったもの。
  2 m × 1.5 m なら 40 × 30 列程度。
* 各列の `floor` / `ceiling` は `container_z_interval` の厳密解から取るので、
  開口部の切り欠き(`cut_x` / `cut_y`)も自動的に入る。
  `points` / `n_vecs` を持たない observation では公称内寸へフォールバックする。
* `top[i,j]` は表面高さ、`filled[i,j]` は柱の実充填高さ。
  `sealed_volume = Σ max(top - floor - filled, 0) × cell_area`。
* 着地点判定は footprint サイズの窓を滑らせて
  「窓内の高低差 ≤ `BOARD_FLATNESS_TOLERANCE`」かつ
  「窓内の最小 headroom ≥ 形状高さ」かつ「窓が全て usable」。

### 既知の近似 — 二つとも保守側

1. **棚下の空間は表現できない。** 2.5D の限界。棚の列は床から棚上面まで
   solid として計上する。結果として、棚の下に置いた荷物は「損害として
   数えられる」のではなく「見えなくなる」。
2. **列は中心でサンプルする。** 1 セルより狭い段差は存在しないことになる。
   着地点を過小に数えるのは、でっち上げるより安全である。

## 探査形状の選び方

visible pool の全アイテム × 全 orientation の footprint を重複除去し、
**面積の大きい順に `BOARD_PROBE_SHAPES`(既定 8)個**。大きい footprint から
着地点を失うので、信号のほとんどはそこにある。

同じ footprint を生む orientation が複数あるとき、必要 headroom は
**その中の最小の高さ**を採る。盤面がその形状を受け入れる最も易しい経路で
評価するため。

## 統合の仕方

`LOOKAHEAD_SELECTION_MODE=board` で `Agent._board_choice` が
`PlacementCore.top_candidates` の上位 K を board 順で並べ替える。

**ランカーが提案し、盤面が処分する。** ここに来る候補は全て inclusion /
搬入経路 / 支持の検証と risk gate を通過済みなので、これは*出荷 agent が
既に置く気だった集合*の並べ替えでしかない。ゲートではない。

`K = 1` は出荷時の決定と完全に同一である。K が board に渡す権限の量になる。

コスト面では既存の `weighted` より**安い**: 候補ごとの `deepcopy` +
`evaluate_visible_pool_feasibility` の再探索がなくなり、代わりに
(格子コピー 2 枚 + 形状数ぶんの窓走査)になる。公式ログの
`policy: 6.533 s`(予算ほぼ使い切り)を踏まえると、この方向でなければ
入らない。

## 測定

`scripts/run_risk_ablation.py` に 2×2:

| arm | `LOOKAHEAD_SELECTION_MODE` | `LOOKAHEAD_TOP_K` |
| --- | --- | --- |
| `base` | weighted | 3 (出荷時) |
| `topk8` | weighted | 8 |
| `board_k3` | board | 3 |
| `board_k8` | board | 8 |

`topk8` は**対照**である。K を広げること自体が決定を変えるので、
`board_k8` が `base` に勝っても board の項の手柄とは限らない。
`board_k3` vs `base` が固定 K での純粋な選択規則の差、
`board_k8` vs `topk8` が広い K での同じ差になる。

### 結果を読む前の標準警告

development suite のノイズ床は既測で **placed sd 2.3–2.7、range 7–9**
(`docs/` の noise floor 節)。5 config の合計差がこの帯に収まるなら、
それは結果ではない。config 別の内訳なしに合計を読まないこと。

`aabb-cache-guard-mixed` が前例である: 候補スループットを 6.4 倍にしたら
**混合**の結果(+10 / −12)が出た。飢えた探索が偶然の正則化として働いて
いたためである。選択規則の変更も同じ族に属する。

## 結果(2026-08-02、36 episodes)— 混合。既定は変えない

上の警告が当たった。`LOOKAHEAD_SELECTION_MODE` の既定は `weighted` のまま。

同時走行の base に対する paired 2 ブロック(`board_k3`、K は出荷値 3)。

| case | base ×2 | board ×2 | 差 | 判定 |
| --- | --- | --- | --- | --- |
| b000-k15 | 17, 17 | **23, 16** | +6, −1 | board 側が 7 動く(既知ノイズ幅そのもの) |
| b000-k20 | **14, 17** | 17, 17 | +3, 0 | base 側が 3 動く |
| b000-k40 | 18, 17 | 22, 22 | +4, +5 | **再現する勝ち** |
| b001-k20 | 18, 18 | 13, 14 | −5, −4 | **再現する負け** |
| b001-k30 | 17, 17 | 21, 21 | +4, +4 | **再現する勝ち** |
| 合計 | 84, 86 | 96, 90 | +12, +4 | |

10 pair で 6W/3L/1T、符号検定 p = 0.508。

**per-config の内訳が結果であって、合計ではない。** ブロック 1 の +12 という
見出しは、再現しなかった b000-k15 の +6 が担いでいた。安定な 3 config では
**+4.5 の勝ちが 2 つ、−4.5 の負けが 1 つ**で、正味 +4 程度 — suite の
ノイズ帯の中である。不安定な 2 config も「効果なし」ではなく
**どちらかの arm が動いている**ので、そこからは何も読めない。

b001-k20 の負けには機序がある(再現するので)が、まだ分かっていない。
release 着地高さの修正はこの config を狙って入れたのに、**1 悪化した**。

### 副次的に確定したこと

* **対照は効いた。** `topk8` は 5 config 中 3 つで base と完全一致し、trace 上
  immediate score が小数 4 桁まで同じで item index だけ違う。アイテム列に
  互換な同型物が多いためで、**K を広げること自体はほぼ何もしない**。
  よって board arm の差は選択規則の差であり、候補集合の広さではない。
* **board 規則は出荷版より安い。** policy 最大 5.03 s(base は 6.53 s)。
  候補ごとの `deepcopy` + 再探索が消えるため。ただし local の探索締切は
  `policy_timeout 8.0 − LOOKAHEAD_TIME_RESERVE_SECONDS 1.5 = 6.5 s` で、
  公式ログの `policy: 6.533 s` はこれと一致する。つまり**公式 run も 8 s
  制限ではなくこの reserve に当たっている**。board mode が 3 s 使い残すのは
  利益ではなく未使用予算である。
