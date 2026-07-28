# Lookahead comparison history

この領域は `weighted`、`depth2`、`pool_resilience` の配布PyBullet
スナップショット比較専用。
通常のhandoff、`theory`、`experiments` profileからは読み込まない。

実行:

```powershell
python scripts/compare_lookahead.py
```

出力:

- `latest-summary.md` / `latest-summary.json`: 直近比較の短い表
- `history/<run-id>/summary.*`: 実行時点の比較要約
- `history/<run-id>/<mode>/evaluation_results.json`: 公式評価JSON
- `history/<run-id>/<mode>/simulator.log`: モード別の生ログ
- `history/<run-id>/<mode>/agent_policy_trace.jsonl`: action選択時の残余可行率

actionごとの診断:

- 直接値: 累積配置数、体積、質量重心z、残容量
- proxy: AABB heightmapの表面TV・標準偏差・平坦edge比率
- agent proxy: 仮想配置後に、評価対象の可視pool荷物がまだ可行である割合

直接値とproxyは別々に記録し、未知の公式重みで合成した総合scoreは作らない。

結果の解釈:

- `is_included`、`is_valid`、`is_placed_safe`が全ケースtrueの場合だけ、
  有効なサンプルスコアとして比較する。
- 物理判定がfalseの場合も履歴は残すが、fillと配置数は診断値とする。
- 比較は同一Git SHA、同一config、同一seed、同一CPUジョブ内で行う。
- `fill_score`と配置数は代理指標であり、低重心、priority/soft penalty、
  非公開scene、完全な動的安定性を含むリーダーボードscoreではない。
- 履歴を通常コンテキストへ昇格させる場合は、再現コマンドとGit SHAを明記する。

競技全体の評価契約は `python scripts/context.py show competition` で確認する。
