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

完全な定式化、限界、実験計画は `PREVIEW_RESIDUAL_VALUE.md` を読む。
