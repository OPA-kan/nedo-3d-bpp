# 第1パスの深さ: `ANCHOR_FIRST_PASS_ATTEMPTS` 64 → 256

**採用済み**(2026-08-02)。既定を変更した。撤回は 1 行。

## なぜ

候補探索は (item, orientation, container) の unit を幅優先で回り、第1パスで
各 unit に `ANCHOR_FIRST_PASS_ATTEMPTS` 回だけ試す。狙いは「1 個の実行不能な
unit が予算を食い潰すのを防ぐ」ことだった。

`reports/same-class-stacking` の probe で、**その深さが候補の存在する深さに
届いていない**ことが分かった。候補ゼロで死んだ終端状態で:

| attempts/item | 置ける item 数 (b000-k40 step18, visible 23) |
| ---: | --- |
| 16 | 0 |
| 64 | **0** ← 出荷時の第1パス |
| 256 | **6**(pool 全体で 1.94 s) |
| 1024 | 6 |
| 4096 | 6 |

live 側は同じ step で 6.5 s 持ちながら `units 1/120 completed` で 0 候補。
**合法手は残っていたのに探索が届いていなかった。** 崖は 64 と 256 の間にあり、
1024/4096 で増えないので 256 は曲線の膝である。

## 測定

`base(=64)` / `first_pass128` / `first_pass256` を development 5 config で
paired 2 ブロック(30 episodes)。

### placed

| case | 64 | 128 | 256 |
| --- | ---: | ---: | ---: |
| b000-k15 | 17 / 17 | 20 / 20 | 19 / 19 |
| b000-k20 | 13 / 13 | 17 / 17 | 17 / 17 |
| b000-k40 | 12 / 12 | 16 / 16 | 16 / 16 |
| b001-k20 | **11 / 16** | 16 / 16 | **19 / 16** |
| b001-k30 | 16 / 16 | 17 / 17 | 20 / 20 |
| 合計 | 69 / 74 | 86 / 86 | 91 / 88 |

10 pair 対 base で **128 は 9W/0L/1T (+29)、256 も 9W/0L/1T (+36)**、
符号検定 **p = 0.0039**。唯一の引き分けは b001-k20 のブロック 2。

**b001-k20 以外の 4 config は両ブロックで完全に同一値**。動くのは
b001-k20 だけで、base が 11↔16、256 が 19↔16 と振れる。前ブロックで
「base が 18 → 11 に動いた」謎はこの config の不安定性である。

### fill

64: 86.8 / 90.1 → 128: 112.6 / 112.6 → 256: 111.5 / 106.8。両 arm とも大幅増。

## 決め手 — 仕事量は増えていない

| arm | attempts/step 平均 | policy 最大 |
| --- | ---: | ---: |
| 64 | 7649 | 6.537 s |
| 128 | 6793 | 6.545 s |
| 256 | 7864 | 6.525 s |

**総試行数も deadline 到達も変わらない。** これは「深く掘って余計に働いた」
ではなく、**同じ仕事の配り方だけを変えた**結果である。
`attempts_to_first_candidate` 中央値は 644 → 1133 → 1823 で、買った深さは
実際に使われている。

## 128 ではなく 256 を採った理由

placed で 256 が +36 対 +29。b001-k20(唯一の不安定 config)を除くと差は
**両ブロックとも +14 対 +12** で、小さいが再現する。fill は逆に 128 が
+3.7 良い。

公式スコアの構造上、placed は cog / stability / placement / soft の
**ゲート**(`docs/COMPETITION_QA.md:9`)であり fill は 1 成分にすぎないので、
placed を採った。加えて probe の曲線が 256 で平らになるので、256 は恣意的な
点ではなく膝である。

## 事前に指摘されたコストは実在する

**breadth↓ / depth↑** の懸念はそのとおりで、序盤の
`items_with_candidates` 平均は **9.64 → 8.74 → 8.28** と全 config で低下する。
それでも placed は全 config で上がった。トレードは成立している。

## fallback 死は減っていない。増えた

| | 64 | 128 | 256 |
| --- | ---: | ---: | ---: |
| fallback 死 / 10 episodes | 3 | 6 | 4 |

これは**前進の副産物**である。終端の内訳を見ると:

* **64 は `placement_core` + `is_placed_safe False` で死ぬ**(ブロック1で 5 中 4)。
  step 12–18 で物理的に崩れる。fallback に**到達していない**。
* **256 は fallback で死ぬ**(5 中 3)。崩れずに step 17–21 まで生き、
  最後に手が無くなる。

死因が「早期の転倒」から「終盤の手詰まり」へ移った。当初の判定基準は
「fallback 死が減る」だったが、そもそも base はそこまで生きていなかった。

## Task A(オフライン有効)への波及 — 確認済み

`optimize()` は `DryRunEvaluator` → `replay_placement_trace` →
`PlacementCore.choose` と辿るので、**この定数はオフライン探索にも効く**。
development 5 config は全て `optimize: false` で測ったので、そこは
測定範囲外だった。投稿前に別途確認した(`reports/first-pass-depth-taskA`):

| arm | placed | fill | optimization | policy |
| --- | ---: | ---: | ---: | ---: |
| `first_pass64` | 20 | 30.176 | 109.27 s | 6.518 s |
| `first_pass256` | 20 | 30.176 | 118.70 s | 6.515 s |

**結果は完全に同一**(placed も fill も小数 3 桁まで)。オフラインの
事前並べ替えが効いている Task A では、各手の最良候補が 64 試行以内に
見つかるため深さが効かない。

時間は **109 → 119 s** と 9.4 s 増えたが、`OFFLINE_SEARCH_BUDGET_SECONDS`
150 s の内側であり、公式上限 180 s に対して **61 s の余裕**がある。
オンライン側は 6.52 s(上限 8 s、README 推奨の「1 秒以上の余裕」を満たす)。

つまり **Task A では中立、Task B(オンラインのみ)で +25%** という形になる。

## 残るリスク

* development 5 config は source 2 本(000 / 001)から生成したもので、
  **般化は未検証**。final_holdout は protocol どおり手つかず。
* b001-k20 は base も 256 も振れる。この config だけ機序が別にある。
* 序盤 breadth の低下が、より長い item stream や別のコンテナ形状で
  支配的になる可能性は測っていない。

## 撤回と再測定

既定に戻すには `ANCHOR_FIRST_PASS_ATTEMPTS` の既定値を 64 へ。
旧挙動は `first_pass64` arm として残してあるので、回帰チェックは
`run_risk_ablation.py --arm first_pass64` で常に取れる。
