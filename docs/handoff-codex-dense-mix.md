# Codex への引き継ぎ: Task A の dense-mix 越え（2026-10-19）

ブランチ `claude/rl-packing-policy-ftogt3`（head はこのファイルを追加したコミット）。
このファイルは現状説明と次のタスクの仕様。作業はこのブランチから切った
`codex/dense-mix` 等の自分のブランチで行い、push する。

## 1. 現状（プラットフォーム）

公式スコア = 0.287 fill + 0.219 cog + 0.210 stability + 0.143 placement + 0.141 soft。
エピソードの置けた個数が過半に届かないと fill 以外が 0 になる（count gate）。
stability は採点されたエピソード数 × 4.1775 の格子に乗る（`reports/wedge/stability-lattice.md`）。

| build | 総合 | fill | cog | stab | place | soft | counted | 備考 |
|---|---|---|---|---|---|---|---|---|
| v57形（planner単独の診断） | 56.43 | 38.66 | 64.83 | 77.94 | 51.15 | 52.4 | 19/23 | A の基準 |
| v59（+ dense plan + priority strip） | 56.25 | 38.66 | 64.04 | 78.04 | 52.05 | 51.25 | 19 | dense plan は何も変えず |
| v60（v59 + B の content levers） | **58.01** | 35.25 | 65.82 | 74.68 | 63.0 | 61.8 | 18 | 最高。B を1本落として +1.76 |

エピソード構成（3つの surrender 診断からの推定、`reports/wedge/findings.md` の
"Correction to the composition reading"）: N=23、B 11本（全採点）、C 3本（全採点）、
A 9本のうち 5本採点・**4本未採点**。未採点 A は fill 約45・placed 約0.42。
サンプル mix の c1 容器なら 80 個級（閾値41、33個置けている）で、
ベンチの `dense-a` c1x80 では dense plan が 11/12 越えるのに、プラットフォームでは
dense plan が plain に一度も勝たなかった（v59 の fill が v57 と小数2桁まで同一）。
**結論: 未採点 A はサンプル mix・c1 ではない。mix か容器が違う。** 何かは未観測。

体積の下限（サンプル mix・c1、最小 N/2+1 個の体積 / 容器体積）: 80個 0.43、
100個 0.54、120個 0.64。越えた実績の最高は 0.506、最終 fill の p90 は 0.46。
100個級は限界、120個以上は不可能。未採点4本がそこまで大きい証拠はない。

## 2. 直近で測って不採用になったもの（繰り返さないこと）

- `reports/wedge/a-mix.md`: dense plan の固定寸法（縦置き上限 0.55/0.40 m、
  行奥行き表）を積荷から導出する `plan_count_secure_dense_adaptive` 等。
  dense-a・公式サンプルではプラン不変だが dense-mix-a で +0.04（12→12）、hard-a −1.28。
  原因: 天井 1.3〜1.5 m に縮小した容器では soft の headroom reserve が縦置き層を
  潰す（51 プラン中 36 が「縦置き層なし」）、big mix には縦置き姿勢が無い。
- 同報告: `plan_count_secure_fill_first`（閾値不達なら fill で順位付け、dense を飛ばす）。
  huge-a（100〜160個）で fill 39.0→33.4。dense plan が体積も一番運ぶので飛ばすと損。
  dense を残す形は無害無益。130〜160個では v59 形の optimize が最大 139.6 s
  （140 s 予算に接触）という時間の問題だけ残る。
- `reports/wedge/bc-mix.md`、`b-keep-count.md`: B/C の分布更新と B の越え回収。全部不採用。
- それ以前の A: `a-dense.md`、`a-dense-quality.md`、`a-soft-frame.md`、`a-count-secure.md`、
  `cliff-veto.md`、`pair-reserve.md`、`a-tail-order.md`。findings.md の末尾 30 節に要約あり。

## 3. 次のタスク: dense-mix-a で越える

スイート `dense-mix-a`（`bench/scenes.py` `make_dmix_scene`、48 scene）: 単一容器を
長さ 0.85–1.25×、幅 0.85–1.15×、高さ 0.85–1.2×、chamfer 0.7–1.3× に縮尺、
60〜90 個、mix は sample/big/small/extra、soft 比率 0.1–0.6、priority 率 0–0.3。
出荷形（`reports/bench/arms/arm_adenser_a.txt` + `offline_budget_seconds=30`）の記録
`reports/bench/adenser30-dense-mix-a` は **12/48 しか越えない**。mix 別の内訳は
a-mix.md の表。これがプラットフォームの未採点 A の型かは分からないが、
ベンチ上で明確に負けている 48 本であり、sample mix・c1 以外で勝てる構造を作るのが目的。

手順:
1. 記録から、未採点 36 本ごとに mix・容器倍率・soft 率・priority 率・個数・閾値・
   各 variant のプラン個数（記録 json の `count_secure_log`）・replay 後の個数・
   `frame_demand`（最小 N/2+1 個の体積比）を表にする。demand > 0.51 は
   「体積的に無理」として除外し、残り（届くのに逃している群）の共通点を出す
   （低天井か、big 箱か、soft 率か）。
2. 残り群の代表 3〜4 本でプランのログ（`plan_dense` の info: flat/ledge/standing/soft）
   を読み、クラスごとの束縛を名指しする: headroom reserve、縦置き上限、
   低天井での平層数、縮尺 chamfer での ledge 形状、soft-on-soft の cap、carry-in の帯。
3. 束縛ごとにレバーを作る（`rule_alpha/config.py` のフィールド、既定オフ、docstring、
   `tests/test_count_secure.py` にテスト）。候補: 縦置き層が入らない天井では第3平層、
   dense plan 内でだけ reserve を緩める、big 箱の平敷き＋soft 直載せ、
   容器の実 chamfer から ledge を計算。**どのレバーも公式サンプルと dense-a の
   プランを変えないこと**（レバー on でプランが同一というテストを付ける）。
4. CI で測る（下記）。arm は `arm_adenser_a` + フィールド、`dense-mix-a` を
   `adenser30-dense-mix-a` と比較。最良 arm は `dense-a`/`core-a`/`hard-a` も
   `adenser30-*` と比較。合計 8 run まで。
5. 判定: dense-mix-a の越え 12 → ?（クラス別）。A の出荷規則: dense-a/core-a/hard-a で
   越え損なし・転倒エピソード増なし・サンプル mix のプラン同一。
   報告 `reports/wedge/a-dense-mix.md`、findings.md 末尾に 1 節、
   `reports/bench/arms/README.md` に arm の行。

## 4. 規約（必読）

- `agent/agent.py`、`simulator/agent.py`、`simulator/` 以下は変更禁止（読む・走らせるは可）。
  `simulator/agents/submit_*`、`simulator/results_*` はコミットしない（作ったら削除）。
- `submission/agent.py` は出荷担当が触る。提案は arm ファイル
  （`reports/bench/arms/arm_<name>_a.txt`、1行）で。
- 新しい挙動は必ず config フィールド、既定オフ、既存テストと出荷 arm のプランは不変。
- Python は `.venv312/bin/python`。テスト:
  `python -m unittest tests.test_rule_alpha tests.test_agent tests.test_bench tests.test_count_secure tests.test_fastgeom`
- ローカル bench: `python -m bench run --arm "$(cat reports/bench/arms/<arm>.txt),offline_budget_seconds=30" --suite dense-mix-a --out reports/bench/<out> --budget 4.5 --sim physics`
  （48 scene の physics は数時間。`--scene A:dmix:<seed>`、`--sim analytic` で探る）。
- CI（本計測、6 shard）: ブランチを push してから `bench-run.yml` を dispatch。
  ```
  python3 - <<'EOF' > body.json
  import json
  arm = open("reports/bench/arms/<arm>.txt").read().strip() + ",offline_budget_seconds=30"
  print(json.dumps({"ref": "<branch>", "inputs": {"arm": arm, "suite": "dense-mix-a", "sim": "physics",
                    "out": "reports/bench/<out>", "shards": "6", "budget": "4.5"}}))
  EOF
  gh api -X POST repos/OPA-kan/nedo-3d-bpp/actions/workflows/bench-run.yml/dispatches --input body.json
  ```
  run 一覧: `gh api "repos/OPA-kan/nedo-3d-bpp/actions/workflows/bench-run.yml/runs?branch=<branch>&event=workflow_dispatch&per_page=10"`。
  artifact は `https://api.github.com/repos/OPA-kan/nedo-3d-bpp/actions/runs/<run id>/artifacts`
  から zip を取り、`reports/bench/<out>/` に展開（record json が scene ごと）。
- 比較: `python -m bench.platform_score reports/bench/<base> reports/bench/<new>`
  （対応 scene の差、bootstrap CI、counted 数、5 成分）。
- 30 s の offline 予算がプラットフォームの 140 s の代理（CI ランナーが遅い）。
- 報告は数値と CI 付きで。「効きそう」ではなく「dense-mix-a +x [lo, hi]、越え 12→y」。

## 5. 参照

- 得点の読み方・格子・組成: `reports/wedge/stability-lattice.md`、findings.md の
  "The platform's composition" と "Correction to the composition reading"。
- dense plan の構造: `rule_alpha/count_secure.py` `plan_dense`、`priority_strip`、
  `adaptive_dense_tokens`、`dense_standing_cap`; `rule_alpha/planner.py`
  `pack_rows`、`_standing_poses`、`manifest_row_depths`。
- 固定数の監査表: `reports/wedge/a-mix.md`。
- 提出記録: `reports/submission/official-results.md`、`docs/submission.md`。
