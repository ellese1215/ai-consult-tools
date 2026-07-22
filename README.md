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

`start`もbundle生成前に同じ構造同期を自動実行します。手動の`structure sync`は、`find`を使う前に索引だけを更新する場合や、bundleを生成せず構造正本だけを同期する場合に使用します。

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

`start`は実行時の構造を走査し、`folder_tree.txt`と`local/cache/repo_structure_index.json`を必要に応じて更新します。構造に一時ファイルや作業用フォルダを残したまま実行しないでください。

通常は`consult.py start`を直接一度実行します。事前の`structure check`、一時設定ファイル、`folder_tree.txt`のハッシュ不変確認、ZIP内部の重複検証を加えた外部wrapperは不要です。古い、欠落、形式不正の`folder_tree.txt`は`start`が再生成し、その更新は正常な処理結果です。

`folder_tree.txt`はパス確認用の補助資料です。`start`は現在構造から再生成した内容をbundleへ自動収録しますが、同期前の鮮度や生成前後の不変性をbundle生成の合否条件にはしません。手動のinclude指定も不要です。

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

Claude:
ai-consult-tools/claude/consult_case/<BundleLabel>/
```

ChatGPTは決定的ZIP、Claudeは結合Markdownまたはpart分割Markdownを生成します。収集結果とmanifestの契約は共通です。

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
