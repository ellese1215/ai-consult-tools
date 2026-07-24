# ai-consult-tools

Git管理されたローカルリポジトリを根拠に、ChatGPT・Claudeとの開発相談を進めるための共通CLIです。

AI相談運用基盤v4では、収集・Git差分・bundle内部モデルを共通化し、ChatGPTとClaudeの違いを最終出力形式だけに限定しています。

> V4共通CLIへの移行と旧構成整理は完了しています。正式バージョンは`python ai-consult-tools/consult.py --version`で確認してください。

## 動作要件

- Python 3.10以上
- Git管理されたリポジトリ
- 外部Pythonパッケージ不要

コマンドはRepoRootで実行します。

```text
python ai-consult-tools/consult.py <command> [options]
```

## セットアップ

### 1. 共通設定を作成する

```powershell
New-Item -ItemType Directory -Force .\ai-consult-tools\local | Out-Null

Copy-Item `
  .\ai-consult-tools\config\consult.config.example.json `
  .\ai-consult-tools\local\consult.config.json

Copy-Item `
  .\ai-consult-tools\shared\consult.local.example.md `
  .\ai-consult-tools\local\consult.local.md
```

`local/consult.local.md`へ、RepoRoot、ビルド・試験コマンド、remote・deployなどのローカル固有情報を記入します。

`config/project_profiles.example.json`が対象リポジトリに合わない場合だけ、次を作成して編集します。

```powershell
Copy-Item `
  .\ai-consult-tools\config\project_profiles.example.json `
  .\ai-consult-tools\local\project_profiles.json
```

`local/`はGit管理しません。設定ファイルへAPIキー、パスワード、トークンなどを書かないでください。

## 基本コマンド

### 構造を同期する

```text
python ai-consult-tools/consult.py structure sync
```

`folder_tree.txt`とローカル構造インデックスを、同一の構造snapshotから同期します。

永続的な構造資料を更新するコマンドは`structure sync`だけです。`start`、`structure check`、`find`は`folder_tree.txt`とローカル構造インデックスを書き換えません。

確認だけを行う場合：

```text
python ai-consult-tools/consult.py structure check
```

`structure check`は構造資料だけを診断する任意コマンドです。staleは`start`の実行不能を意味せず、bundle生成前の必須確認には使用しません。

パスを検索する場合：

```text
python ai-consult-tools/consult.py find <query>
python ai-consult-tools/consult.py find <query> --profile <name>
```

### 相談開始用bundleを作る

ChatGPT：

```text
python ai-consult-tools/consult.py start --target chatgpt --profile <name> --case-name <case> --include-set common_rules --include-paths <path>...
```

Claude：

```text
python ai-consult-tools/consult.py start --target claude --profile <name> --case-name <case> --include-set common_rules --include-paths <path>...
```

`--include-paths`には、今回の相談に必要な仕様書、実装、試験だけをRepoRoot相対で指定します。

- `--include-paths`は、選択profileの`scopeRoots`内だけを指定します。
- プロジェクト横断の共通資料は、設定済みの`--include-set`で収録します。

標準の`common_rules`は、次の引き継ぎ用最小運用セットです。

```text
ai-consult-tools/README.md
ai-consult-tools/docs/01_current_spec.md
ai-consult-tools/shared/00_ai_consult_operation_rules.md
ai-consult-tools/shared/02_consult_template.md
ai-consult-tools/local/consult.local.md
```

引き継ぎ用の`start`では`--include-set common_rules`を省略しません。上記5ファイルを`--include-paths`へ個別に重ねず、設定済みinclude setから収録します。これにより、次の相談先は今回のプロジェクト資料に加えて、使用中の相談ツールの役割、現行CLI仕様、共通フロー、依頼形式、ローカル固有条件を確認できます。

`start`は実行時の構造を一度走査し、そのlive inventory snapshotからbundle内の`PROJECT_TREE.md`と`folder_tree.txt`を生成します。RepoRoot上の`folder_tree.txt`と`local/cache/repo_structure_index.json`は作成、修復、更新しません。

通常は`consult.py start`を直接一度実行します。事前の`structure check`や一時設定ファイルは不要です。永続構造資料が`current`、`stale`、`missing`、`invalid`のどの状態でも`start`を実行でき、実際の開始時状態と取得可能なprofile内差分を`STRUCTURE_STATUS.md`へ記録します。

`folder_tree.txt`はパス確認用の補助資料です。bundle内の同名itemはlive snapshotから生成され、永続ファイルの読直し結果ではありません。RepoRoot上の既存`folder_tree.txt`は`start`前後でbyte-identicalに維持されます。bundle内itemの手動include指定は不要です。

### 変更をレビューする

ChatGPT：

```text
python ai-consult-tools/consult.py review --target chatgpt --profile <name> --case-name <case> --target-paths <path>...
```

Claude：

```text
python ai-consult-tools/consult.py review --target claude --profile <name> --case-name <case> --target-paths <path>...
```

`review`はstaged、unstaged、未追跡を区別して収集します。対象パスを明示し、無関係な変更を混ぜないでください。ignore対象のローカルファイルは、完全なファイルパスを明示した場合だけ未追跡項目として収録します。明示対象に変更がない場合または対象が存在しない場合も、`SKIPPED.md`へ理由を記録して黙って省略しません。

## 旧スクリプト互換入口

旧ファイルパスからの移行用に、次の薄い互換ラッパーを残します。新しいコマンドや運用では`consult.py`を使用してください。

```text
ai-consult-tools/chatgpt/consult_bundle_chatgpt.py
ai-consult-tools/claude/consult_bundle_claude.py
```

互換入口では`--profile`が必須です。ChatGPT版は`chatgpt`、Claude版は`claude`へ出力targetを固定し、旧4モードを次の現行コマンドへ変換します。

| 旧モード | 現行処理 |
|---|---|
| `map` | 構造資料だけを収める`start` |
| `repo` | 選択profileの`scopeRoots`を収集する`start` |
| `include` | 指定対象を収集する`start` |
| `diff` | staged、unstaged、未追跡を収集する`review` |

旧設定schema、旧出力形式、staged限定、unstaged限定、任意ref間diff、旧basename検索、絶対パスincludeは維持しません。未対応指定は成果物生成前に終了コード2で拒否します。

## 出力

既定の出力先は以下です。

```text
ChatGPT:
ai-consult-tools/chatgpt/consult_case/<BundleLabel>/<BundleLabel>.zip
ai-consult-tools/chatgpt/consult_case/<BundleLabel>/<BundleLabel>.zip.sha256

Claude:
ai-consult-tools/claude/consult_case/<BundleLabel>/
```

ChatGPTの正式成果物は決定的ZIPとSHA-256 sidecarの2点、Claudeは結合Markdownまたはpart分割Markdownです。sidecarは`<64桁の大文字SHA-256> *<ZIP basename><CRLF>`のUTF-8 BOMなし1行で、同じディレクトリのZIPだけを検証します。ZIPとsidecarは一時ディレクトリ内で完成・検証後に同時確定されます。

ChatGPT成功時は従来の`start: created`／`review: created`、`target:`、`bundle:`、`output:`に加え、`bundle_path:`、`bundle_sha256:`、`sidecar_path:`、`sidecar_match: true`を出力します。wrapperは成果物名を推測せず、これらの行を使用します。

設定された`outputs.chatgpt.outRoot`と`outputs.claude.outRoot`は生成物専用領域です。既定値か任意値か、現在のtarget、tracked／untrackedを問わず、各outRoot自体と全子孫を構造走査、start本文収集、reviewのGit差分・未追跡収集から無言で完全除外します。outRootはglobではなく、`[`なども文字として扱うRepoRoot相対のリテラルなディレクトリ境界です。一般の`filters.excludePaths`とは別に判定するため、自動除外した成果物パスを`SKIPPED.md`へ記録しません。

`--include-paths`、include set、reviewの`--target-paths`でoutRoot自体または子孫を明示指定すると、正式成果物を作らずエラー終了します。outRoot外の正規ソースはリポジトリ相対パスと本文を維持し、現在生成した成果物を受け取るためのCLIの`output:`およびChatGPT専用4行も維持します。ツールは既存成果物を削除、移動、上書きしません。

## 基本フロー

```text
必要に応じて structure sync
→ start bundle
→ 参照確認
→ 仕様・変更範囲・受入条件の合意
→ 文書・実装
→ 試験
→ review bundle
→ commit
→ push
```

bundleは生成時点の参照スナップショットです。恒久的な仕様正本ではありません。

## 文書

| 文書 | 役割 |
|---|---|
| `shared/00_ai_consult_operation_rules.md` | 共通の相談・変更・レビュー運用 |
| `shared/02_consult_template.md` | Work・Codex・review・handoffの最小テンプレート |
| `docs/01_current_spec.md` | 共通CLI、設定、bundle、出力の現行技術仕様 |
| `shared/SECURITY.md` | 除外、機密情報、生成物の取扱い |
| `shared/consult.local.example.md` | Git管理外のローカル文書テンプレート |
| `config/consult.config.example.json` | 共通設定例 |
| `config/project_profiles.example.json` | プロジェクトプロファイル例 |

`chatgpt/`と`claude/`には、旧ファイルパスから現行共通CLIへ移行するための互換ラッパーだけを残しています。旧モデル別仕様書、README、ガイド、テンプレート、設定例は削除済みです。

## バージョンと配布

バージョンの正本は`src/ai_consult/__init__.py`の`__version__`です。

```text
python ai-consult-tools/consult.py --version
```

通常配布対象はpublicリポジトリの追跡ツリーです。clean exportは同じ追跡ツリーを`git archive`したZIPとし、Git管理外の`local/`、cache、archive、`consult_case/`、秘密情報を含めません。

## セキュリティ

bundleはソースコード、差分、ローカル固有情報を含む場合があります。生成前と外部共有前に対象・`SKIPPED.md`・`MANIFEST.csv`を確認してください。

詳細は`shared/SECURITY.md`を参照してください。

## ライセンス

MIT License
