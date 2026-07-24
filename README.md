# ai-consult-tools

Git管理されたローカルリポジトリから、AI相談の開始資料と変更レビュー資料を再現可能な形で生成する共通CLIです。
ChatGPT向けZIPとClaude向けMarkdownを、同じ収集・差分モデルから作成します。

## 動作要件

- Python 3.10以上
- Git管理されたリポジトリ
- 外部Pythonパッケージ不要

コマンドはRepoRootで実行します。

```text
python ai-consult-tools/consult.py <command> [options]
```

## セットアップ

共通設定例とlocal文書例を、Git管理外の`local/`へコピーします。

```powershell
New-Item -ItemType Directory -Force .\ai-consult-tools\local | Out-Null

Copy-Item `
  .\ai-consult-tools\config\consult.config.example.json `
  .\ai-consult-tools\local\consult.config.json

Copy-Item `
  .\ai-consult-tools\shared\consult.local.example.md `
  .\ai-consult-tools\local\consult.local.md
```

`local/consult.local.md`へRepoRoot、OS／Shell、主要なbuild／testコマンド、詳細runbookへの参照を記入します。

対象プロジェクトの配置が設定例と異なる場合だけ、プロジェクトプロファイルも作成します。

```powershell
Copy-Item `
  .\ai-consult-tools\config\project_profiles.example.json `
  .\ai-consult-tools\local\project_profiles.json
```

`local/`へAPIキー、パスワード、トークンなどの秘密情報を記録しないでください。

## Quick start

通常のプロジェクト相談では、共通契約と案件の現在状態を渡します。

```text
python ai-consult-tools/consult.py start \
  --target chatgpt \
  --profile <name> \
  --case-name <case> \
  --include-set common_rules \
  --include-paths <project-handoff-current> <required-path>...
```

AI相談ツール自体の保守では、技術資料のinclude setを追加します。

```text
python ai-consult-tools/consult.py start \
  --target chatgpt \
  --profile ai_consult_tools \
  --case-name <case> \
  --include-set common_rules \
  --include-set ai_consult_maintenance \
  --include-paths ai-consult-tools/docs/handoff/current.md <target>...
```

変更後は、実際に変更したパスだけでreview bundleを作ります。

```text
python ai-consult-tools/consult.py review \
  --target chatgpt \
  --profile <name> \
  --case-name <case> \
  --target-paths <changed-path>...
```

プレースホルダーは実在値へ置換して実行してください。

## 基本コマンド

### パス検索

```text
python ai-consult-tools/consult.py find <query>
python ai-consult-tools/consult.py find <query> --profile <name>
```

### 構造資料

```text
python ai-consult-tools/consult.py structure check
python ai-consult-tools/consult.py structure sync
```

`structure check`はread-only診断、`structure sync`は`folder_tree.txt`とlocal構造indexの同期です。
`start`はlive snapshotからbundle内の構造資料を作るため、事前のstructure syncを必要としません。

`start`と`review`の基本形はQuick startを参照してください。
`review`はstaged、unstaged、未追跡を区別し、ignore対象のlocalファイルは完全相対パスを個別に指定します。

### 標準include set

`common_rules`は、通常の引き継ぎで常時必要な次の3文書です。

```text
ai-consult-tools/shared/00_ai_consult_operation_rules.md
ai-consult-tools/shared/02_consult_template.md
ai-consult-tools/local/consult.local.md
```

`ai_consult_maintenance`は、ツール保守時にREADME、現行技術仕様、詳細手順、SECURITY、local文書例を追加します。
`repository_structure`はプロジェクト横断の構造資料が必要な場合だけ使用します。

## 出力

既定ではChatGPT向け成果物を`ai-consult-tools/chatgpt/consult_case/`、Claude向け成果物を`ai-consult-tools/claude/consult_case/`へ生成します。
出力形式、決定性、sidecar、outRoot境界は`docs/01_current_spec.md`を参照してください。

## 文書索引

| 文書 | 役割 |
|---|---|
| `shared/00_ai_consult_operation_rules.md` | Work→Codex→WorkとUser判断の最上位契約 |
| `shared/01_ai_consult_procedures.md` | bundle、受渡し、修正ラリー、Git前後の詳細手順 |
| `shared/02_consult_template.md` | 共通工程状態と依頼テンプレート |
| `docs/handoff/current.md` | AI相談ツール保守の現在工程状態 |
| `docs/01_current_spec.md` | CLI、設定、構造、bundle、出力の現行技術仕様 |
| `shared/SECURITY.md` | 除外、機密情報、生成物の取扱い |
| `shared/consult.local.example.md` | Git管理外local文書のテンプレート |
| `config/consult.config.example.json` | 共通設定例 |
| `config/project_profiles.example.json` | プロジェクトプロファイル例 |

## セキュリティ

bundleにはソース、差分、ローカル情報が含まれる場合があります。
生成前と外部共有前に対象、index、skip、manifestを確認してください。
詳細は`shared/SECURITY.md`を参照してください。

## バージョンと配布

バージョンの正本は`src/ai_consult/__init__.py`の`__version__`です。

```text
python ai-consult-tools/consult.py --version
```

通常配布はpublicリポジトリの追跡ツリーを対象とします。
Git管理外の`local/`、cache、archive、`consult_case/`、秘密情報は配布へ含めません。

## ライセンス

MIT License
