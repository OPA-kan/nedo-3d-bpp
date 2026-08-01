# AI context router

このリポジトリでは、最初から全資料を読み込まない。作業対象に合う
context profileだけを段階的に取得する。

`AGENTS.md`（このファイル）は**手順**、`HANDOFF.md`は**現在地**である。
手順は安定しているが現在地は毎回変わる。両方読むこと。

## 開始手順

### Step 0 — 同期する（最初に必ず）

```bash
git fetch --all --prune
git log --oneline --decorate -10
git switch --track origin/experiment/anchor-recall-oracle  # 未追跡なら
# 既にローカルbranchがあるなら: git switch experiment/anchor-recall-oracle
```

worktreeがdirtyなら**switchしない**。作業を退避するか、別worktreeを
**必ずローカルbranch付きで**切る（branch無しだとdetached HEADになり、
閲覧はできてもcommit/pushの作業導線として危険）:

```bash
git worktree add -b work-<topic> ../nedo-trunk \
  origin/experiment/anchor-recall-oracle
cd ../nedo-trunk
cat AGENTS.md   # switch後は必ず明示的に読み直す（自動再読込は保証されない）
```

以降のコマンドは `python3` と書く。環境によって `python` はPATHに無い
（Codex系sandboxで実測）。Windowsのみ `python` に読み替える。

**`main`は正本ではない。** live trunkは`experiment/anchor-recall-oracle`で、
`main`は48コミット以上遅れている。`agent/agent.py`だけで2,600行以上の差がある。
fetch前はremoteに`main`しか見えないことがあり、そのまま読むと**存在しない
実装について推論することになる**。実際にその事故が起きている。

### Step 1 — 現在地を読む（約11 KB）

```bash
python3 scripts/context.py list
python3 scripts/context.py show handoff
python3 scripts/context.py show operations   # 日々の作業ループ規則（必読）
```

測定済みの事実は `python3 scripts/context.py evidence --topic <t>`、
コードの単一関数は `python3 scripts/context.py symbol <名前>` で引く。
複数ジョブは `scripts/run_queue.py` の計画ファイルで一括実行する。
詳細は `docs/AGENT_OPERATIONS.md`。

**現在の live 方策(2026-07-31 の final_holdout 評価で切り替え済み):**
`agent.py` の出荷デフォルトは risk-on — 実 action は
`Q - 1.0 * P_rot`(力学モデル `mech-dev-v1-20260731`)で選択される。
`RELEASE_RISK_LIVE_RERANK=0` で切り替え前の挙動に戻る。滑り項
(`RELEASE_RISK_SLIDE_LAMBDA`)は既定 0 で shadow 検証中。経緯と制約は
`docs/RELEASE_RISK_PROTOCOL.md` §8。**「baseline」は risk-on 方策を指す。**

`HANDOFF.md`の次の3節は必ず読む。

- `Established by evidence` — 各項目にrun IDかコード行が紐付いた測定結果
- `Not established` — **同じくらい重要**。まだ言えないことの一覧
- `Next engineering task` — 現在の課題と、着手してよい順序

### Step 2 — 領域を1つ選ぶ

全部読ませない。`--full`は実装判断に詳細が要ると分かってからにする。

| profile | summary | `--full` | いつ |
|---|---:|---:|---|
| `agent` | 9 KB | **167 KB** | 配置ロジックを変える |
| `simulator` | 3 KB | 109 KB | 公式validatorの挙動を疑う |
| `theory` | 3 KB | 30 KB | 数学モデルの位置づけ |
| `abc-spec` | 10 KB | 10 KB | A/B/Cの実装契約と診断メトリクス |
| `preview-value` | 10 KB | 37 KB | lookahead・残余価値 |
| `replay-dataset` | 8 KB | 68 KB | counterfactual replayの抽出設計とラベル契約 |
| `competition` | 5 KB | 5 KB | 公式I/O・スコア・制限時間 |
| `overview` | 3 KB | 11 KB | リポジトリ全体の目的 |
| `experiments` | 1 KB | 17 KB | 過去runの読み方 |
| `preview-experiments` | 2 KB | 2 KB | lookahead比較の手順と履歴 |

`agent --full`は`agent.py`約4,400行を含む。最初に読むとcontextを使い切る。

`agent/`、`simulator/`、`docs/theory/` の各`AGENTS.md`に領域別の追加手順がある。

### Step 3 — 手を動かす前に

```bash
python3 -m unittest discover -s tests
```

テスト件数は増え続けるので数を当てにしない。読むべきは**skip数**である。

**Python 3.12以上が必須。** `simulator/src/ground_handling/validator.py`が
PEP 701のf-stringを使うため、3.11以下では`SyntaxError`でimportに失敗する
（3.13でも可）。**正式な検証環境はLinux（CI）である。** Windowsローカルは
提出コードの実行はできるが、テストのgreenは保証しない（path separator等の
環境差）。Windowsで失敗したら、まずCIの同一コミットの結果を見る。
さらに**3.12でもPyBullet未導入なら物理統合テスト3件はskipされる**
（`OK (skipped=3)`）。skipが出た実行は物理契約を検証していない。
物理契約を確かめるにはPyBulletを入れてskip 0で回すか、CIの
`replay-integration` job（`NEDO_REQUIRE_INTEGRATION=1`でskipをエラー化）
の結果を見る。

### Step 4 — 変更したら

```bash
python3 scripts/run_checks.py           # agent変更後は必須
```

CIは毎pushで`unit-tests`と`replay-integration`を回す。後者は
`NEDO_REQUIRE_INTEGRATION=1`により、PyBulletが無い環境ではskipではなく
エラーになる。simulatorベンチマークとTask Bは手動dispatch専用。

## 情報の優先順位

矛盾がある場合は、次の順で扱う。

1. 実行中の公式シミュレータソースと設定
2. 自動テストで固定された契約
3. `docs/GEOMETRY_RULES.md` とAccepted ADR
4. 各領域の `CONTEXT.md`
5. 自動抽出API索引
6. Proposedな理論、過去レポート、Colabアーカイブ

理論資料は探索設計の根拠だが、採用済みADRまたはテストへ反映されるまで
実装契約ではない。過去の成功・失敗レポートも現在の結果として扱わない。

## よくある誤り

いずれも実際に起きたものである。

- **`main`を読む。** Step 0を飛ばすと必ずこうなる。
- **限定された否定結果を一般化する。** 「あるrunでpreview項が選択を変えなかった」
  は「preview価値の寄与はゼロ」ではない。「あるsnapshotで候補列挙を広げても
  選択は変わらなかった」は「探索幅は論点ではない」ではない。`HANDOFF.md`の
  `Not established`が、どこまで言えるかの境界である。
- **artifactにしか無い結果を「無い」と扱う。** 重い生データはActions artifact
  のみに残す設計で、compact summaryだけがcommitされる。git内に見えないことは
  未計測を意味しない。どこに何が残るかは`HANDOFF.md`の`Where results live`。
- **プロセスのexit 0を成功と見なす。** 物理検証は`is_included` / `is_valid` /
  `is_placed_safe`が全てtrueでなければ失敗である。
- **`selected_*`混同行列をgate全体のprecision/recallとして読む。** rankingが
  選択した候補にのみ条件づけられている。反復回数を増やしても解消しない。

## 更新規則

- agent APIや幾何契約を変えたら `agent/CONTEXT.md` も更新する。
- simulatorスナップショットを変えたら `simulator/CONTEXT.md` とAPI索引を確認する。
- 数学モデルの状態を変えたら `docs/theory/CONTEXT.md` で
  Proposed / Accepted / Implementedを明示する。
- `context/manifest.json`には短い入口と詳細資料を分けて登録する。
- 現在地が変わったら `HANDOFF.md` を更新する。固定SHAは書かない。次のコミットで
  腐り、レビュアーを誤ったdiffへ送る。
- agent変更後は `python3 scripts/run_checks.py` を実行する。
