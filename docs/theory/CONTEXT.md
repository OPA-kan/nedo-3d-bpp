# Theory context

## 原問題

荷物集合 \(E\) から、局所図形を構成できる候補部分集合族
\(\mathcal{B}\) を生成し、そのうち互いに競合しない部分族を選んだとき、
後続の配置探索を含む目的関数を最大化する。

重要なのは、全実現可能ブロック族を列挙して厳密集合パッキングを解くことではない。
現在状態で有望な小規模構造だけをオンデマンド生成する。

## 現在の統一像

- EP/EMS: 座標候補を圧縮
- 部分列テンプレート: 荷物順列と探索深さを圧縮
- 外部署名: 内部配置状態を圧縮
- DPOR/独立性: 同値な実行順序を圧縮
- closed-loop Option: 逐次実行可能性を保った時間的マクロ

ブロックは
\(b=(S_b,\pi_b,\rho_b,d_b,\sigma_b)\)。
探索上はマクロだが、評価・実行時には共通配置コアで
\(\pi_b\)を一個ずつ再生する。

## 状態

- 2個の部分列テンプレートはImplemented。
- 3～4個への拡張、署名アブレーション、closed-loop Optionの一般化はProposed。
- 安定性プロキシと物理振動の相関、重み調整、配置コア速度依存は未解決。
- pool-awareな残余価値は別profile `preview-value` で扱う。
  `weighted`、`depth2`、`pool_resilience` の選択機構だけImplementedで、
  可行アンカー面積と学習価値はProposed。
- Mode BのstarvationはCase 001のLinux実runでObserved。
  item 0は19step可視、15stepで候補あり、step 14でtop-K入りしたが未選択のまま、
  step 18で候補ゼロになった。これは§10の
  \(\mu_B:(s,V)\mapsto(i,p)\)、\(V_B(s,V)\)への拡張を支持する。
  `NEDO_POLICY_TRACE_PATH`有効時だけ、item cap、探索開始、候補生成、
  immediate top-K、future probe、選択の各段階を荷物別に累積記録する。
  診断はImplementedだが、方策、class quota、regret rankingは未変更。
  \(\chi_V(s)\)によるidentity-aware署名とregret-aware diversityはProposed。
  重いbefore/after regretは
  pre-action snapshotを使うoffline計測として定義する。
- 課題A/B/Cの修正版実装契約とaction後指標は別profile `abc-spec` で扱う。

完全な定式化が必要な場合だけ `MATHEMATICAL_MODEL.md` を読む。

