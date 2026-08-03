# 朝サマリ(2026-08-04 夜間自走の結果)

## Death-band 辞書式リスクゲート — 夜間で採用候補まで到達

死番(自モデルが P_rot≥0.5 と言う release を実行しようとする番)だけ、
選択を辞書式(settled or P_rot<0.5 → score 最良)に切り替える。既定オフ。

| scene | base placed | gate placed | 備考 |
|---|---|---|---|
| **m2-k15**(2コンテナ83個) | μ22.0 (n=6) | **μ30.6 (n=8)** | 発火runは全てbase最良超え。配分も均衡化 |
| b000-k20 | μ19.7 (n=6) | 緩和前 18.0 → **緩和後 20.0 (n=4)** | timing副作用は0.5s床で解消 |
| b001-k20 | 22 / 24.59 | 21 / **26.92** | −1 placed / +2.33 fill の交換(判定保留) |
| 他4scene | — | 完全no-op | 発火せず |

夜間の追加修正: 残予算0.5s未満で gate 停止(評価自体のdeadline消費が
b000-k20 で μ−1.7 を出していたため。緩和後は base と同水準)。

## あなたの判断が要る点

1. **CI反復**: 採用の最終条件。ただし workflow_dispatch は default branch
   (凍結main)に workflow が無いと登録されない — **Settings → Default branch
   を `experiment/anchor-recall-oracle` に変更**すれば、私の
   `death-band-ablation.yml`(push済)と既存の Anchor search ablation の
   両方が dispatch 可能になります
2. **b001-k20 の交換**(−1 placed / +2.33 fill)の損得 — 公式重み不明のため
   測定では決められない。次の提出フィードバックが最安の検証
3. 多コンテナ scene が公式評価に存在するか — placement 減点規則からほぼ
   確実だが、直接の裏取りは提出のみ

## 経緯の全記録

`reports/l3-l4/two-container-smoke.md`(全ラウンド)、ledger 4件
(first-positive → round1-mixed → round2/3 → 本サマリ)、
branch `claude/l3-l4-allocation-ordering` に全て push 済み。
