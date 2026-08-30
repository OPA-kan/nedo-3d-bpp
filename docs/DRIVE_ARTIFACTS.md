# CI生出力のGoogle Drive退避

## なぜ要るのか

`AGENTS.md` は「重い生データはActions artifactのみに残す設計で、compact
summaryだけがcommitされる」と宣言し、読み手に「git内に見えないことは未計測を
意味しない」と警告している。設計としては正しい。ただしこの設計は、**誰も
確かめていなかった前提**の上に立っていた — artifact置き場が、置いたものを
保持し続けるという前提である。

保持しない。実測:

```
actions/upload-artifact を呼ぶworkflow          18本
そのうち retention-days を指定しているもの        0本
→ 全部がGitHubの既定 90日 を継承する
このリポジトリ最古のCI記録                  2026-08-02
```

つまり10月末から、ablationの判定を支えている生トレースが1runずつ消え始める。
一方でそれを引用しているcompact summaryとevidence台帳はgitに残り続ける。
**引用先が消えた台帳は、引用の無い台帳より悪い。** 裏付けがあるように読める
からである。

このパイプラインはその穴を塞ぐ。生出力をGoogle Drive（期限なし）へ複製し、
Driveのfile idと全ファイルのSHA-256を記録した小さな `drive.json` をcommitする。
後から来た読み手は、生データを取り戻せるだけでなく、**手元の複製がsummaryを
計算した当のバイト列であることを証明できる。**

## 何を変えていないか

`reports/board-receptivity/`、`reports/first-pass-depth/`、
`reports/stability-tradeoff/` にcommit済みの `policy-trace.jsonl` 92本
（約200 MB）は**そのまま**である。これらは死んだログではなく
`scripts/fit_hazard_model.py` 他の**入力データ**で、既定引数がこのパスを
指している。退去させるとfresh checkoutで解析が動かなくなる。判断の根拠は
`docs/REPO_AUDIT.md` §D（clone帯域の問題は存在しない、を実測で示している）。

## 置き場

| 項目 | 値 |
|---|---|
| Driveフォルダ | `nedo-3d-bpp/ci-artifacts` |
| フォルダID | `1bT3bypRgB-npoF0BS-5pMq62FJnujgtu` |
| 階層 | `<実験名>/<run_id>/<runディレクトリ>/<ファイル>` |
| pointer | `reports/<実験名>/history/<run_id>/drive.json` |

環境変数 `NEDO_DRIVE_FOLDER_ID` で退避先を差し替えられる。スクリプトを
編集する必要はない。

## セットアップ

CIは `GOOGLE_SERVICE_ACCOUNT_JSON` secretが**空のあいだスキップする**。
notice を1行出して正常終了するので、未設定でもCIは赤くならない。退避が
始まるのはsecretを入れた時点からである。

### 手順A: サービスアカウント

1. Google Cloud Console でプロジェクトを作り、**Google Drive API** を有効化する。
2. サービスアカウントを作成し、JSON鍵をダウンロードする。
3. Driveの `nedo-3d-bpp/ci-artifacts` フォルダを、そのサービスアカウントの
   メールアドレス（`...@....iam.gserviceaccount.com`）に**編集者**で共有する。
4. GitHub の Settings → Secrets and variables → Actions → New repository secret。
   名前 `GOOGLE_SERVICE_ACCOUNT_JSON`、値は**鍵ファイルの中身そのまま**
   （パスではない）。

**既知の落とし穴。** サービスアカウントは自分が作成したファイルの所有者に
なるが、素のサービスアカウントはDriveのストレージ容量を持たない。個人
（gmail.com）のマイドライブ配下へ書くと `storageQuotaExceeded` で失敗すること
がある。Workspaceの共有ドライブが使えるならそこを退避先にすれば起きない
（ファイルを所有するのは共有ドライブであってサービスアカウントではない）。
使えないなら手順Bを採る。

### 手順B: OAuthリフレッシュトークン（個人アカウント向け）

アップロードを人間のアカウントが所有するので、そのアカウントの15 GBを使う。
上の容量問題は起きない。

1. Google Cloud Console でOAuthクライアント（デスクトップアプリ）を作る。
2. スコープ `https://www.googleapis.com/auth/drive` でリフレッシュトークンを取得する。
3. secretを3つ登録する: `GOOGLE_OAUTH_REFRESH_TOKEN`、
   `GOOGLE_OAUTH_CLIENT_ID`、`GOOGLE_OAUTH_CLIENT_SECRET`。
4. `.github/actions/archive-to-drive/action.yml` の `credentials` 入力を、
   この3つを環境へ渡す形に読み替える。

リフレッシュトークンが両方設定されている場合はそちらが優先される。

## 使い方

```bash
python3 -m pip install -r requirements-drive.txt

# 退避（CIが自動で行う。手で流すこともできる）
python3 scripts/drive_artifacts.py upload \
    --source reports/anchor-fallback/downloads \
    --source reports/anchor-fallback/aggregate \
    --remote anchor-fallback/31569836732 \
    --pointer reports/anchor-fallback/history/31569836732/drive.json

# 生データを取り戻す
python3 scripts/drive_artifacts.py fetch \
    --pointer reports/anchor-fallback/history/31569836732/drive.json

# commit済みpointerが今も解決するか全部見る
python3 scripts/drive_artifacts.py verify
```

`--dry-run` は Drive に触らずハッシュと送信予定だけを出す。認証を通す前に
対象範囲を確かめるのに使う。

## 性質

- **冪等。** SHA-256がDrive側と一致するファイルは送らない。workflowを再実行
  してもデータは二重にならない。
- **中断に強い。** archiveステップは `if: always()` で走る。episodeがこけても
  そこまでの生出力は退避される。
- **fetchは検証する。** ダウンロード後にSHA-256を照合し、食い違えば
  「summaryを計算した入力として扱うな」と言って落ちる。
- **pushは競合しても諦めない。** ablationは束で終わるので、pointerのcommitは
  rebaseして5回まで再試行する。それでも通らなければwarningを出すが、
  ジョブは落とさない。測定そのものは成功しているからである。
