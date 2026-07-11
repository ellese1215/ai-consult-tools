# Claude相談ツール（consult_bundle_claude）

> **旧版資料**
>
> 本書はV4-6まで保持する旧モデル別スクリプト用資料です。現行共通CLIの正本ではありません。
> 現行の利用方法は`../README.md`、技術仕様は`../docs/01_current_spec.md`、運用ルールは`../shared/00_ai_consult_operation_rules.md`を参照してください。

Claude（またはその他のAI）との開発相談を、**Git管理されたローカルリポジトリを根拠に行う**ためのツールセットです。

AIへの「推測による回答」を構造的に防ぎ、コードとドキュメントの実体を一次根拠とした相談フローを実現します。

---

## 特徴

- **4モード対応**：map（軽量地図）/ include（範囲指定）/ diff（差分）/ repo（全体）
- **除外ルールをJSONで管理**：`.git`、`node_modules`、秘密情報ファイル等を自動除外
- **単一MDファイルで出力**：Claudeに添付するだけで根拠確定できる構造
- **secret patternによる情報漏洩防止**：`.env*`、`*.key`、`*.pem` 等を自動スキップ
- **クロスプラットフォーム対応**：Windows / Mac / Linux で動作

---

## ファイル構成


```text
ai-consult-tools/
├── shared/
│   ├── 00_ai_consult_operation_rules.md  # Claude / ChatGPT 共通の運用ルール
│   ├── consult.local.example.md          # プロジェクト固有設定のテンプレート
│   └── SECURITY.md                       # セキュリティ・取り扱い注意事項
├── claude/
│   ├── consult_bundle_claude.py          # バンドル生成スクリプト（本体）
│   ├── consult.config.example.json       # 設定ファイルのテンプレート
│   ├── 01_make_consult_bundle_spec.md    # スクリプト技術仕様
│   ├── 02_consult_template.md            # スレッド開始テンプレート
│   ├── 03_claude_session_guide.md        # セッション開始手順・モード選択ガイド
│   └── consult_case/                     # 生成物の出力先（Git管理外）
└── local/                                # ローカル実設定（Git管理外）
    └── claude/
        ├── consult.config.json           # 除外ルール等の実設定（Git管理外）
        └── consult.local.md              # プロジェクト固有設定（Git管理外）
```

---

## 前提条件

- **Python 3.9 以上** がインストールされていること
  - 外部ライブラリ不要（標準ライブラリのみで動作）
- **Git** がインストールされていること
- 対象リポジトリが `git init` 済みであること（diff モードはコミット履歴が必要）

---

## セットアップ

### 1. ファイルを配置する


`ai-consult-tools/` ディレクトリを対象プロジェクトのリポジトリルート配下に配置してください。

```text
your-repo/
└── ai-consult-tools/
    ├── shared/
    │   ├── 00_ai_consult_operation_rules.md
    │   ├── consult.local.example.md
    │   └── SECURITY.md
    └── claude/
        ├── consult_bundle_claude.py
        ├── consult.config.example.json
        └── ...
```

### 2. 設定ファイルを作成する

まず `local/claude/` ディレクトリを作成します。

```bash
# Mac / Linux
mkdir -p ai-consult-tools/local/claude

# Windows (PowerShell)
New-Item -ItemType Directory -Force -Path ai-consult-tools\local\claude
```

`consult.config.example.json` をコピーして `consult.config.json` を作成し、あなたの環境に合わせて編集してください。

```bash
# Mac / Linux
cp ai-consult-tools/claude/consult.config.example.json ai-consult-tools/local/claude/consult.config.json

# Windows (PowerShell)
Copy-Item ai-consult-tools\claude\consult.config.example.json ai-consult-tools\local\claude\consult.config.json
```

主な設定項目：

| キー | 説明 |
|---|---|
| `outRoot` | 生成物の出力先（リポジトリルートからの相対パス） |
| `ruleFile` | 運用ルールファイルのパス |
| `excludeFolders` | 除外するフォルダ名のリスト |
| `excludeExtensions` | 除外する拡張子のリスト |
| `secretNamePatterns` | 除外するファイル名パターン（機密情報ファイル） |

詳細は `consult.config.example.json` のコメントおよび `shared/SECURITY.md` を参照してください。

### 3. consult.local.md を作成する

`shared/consult.local.example.md` をコピーして `consult.local.md` を作成し、ビルドコマンド等を記載してください。

```bash
# Mac / Linux
cp ai-consult-tools/shared/consult.local.example.md ai-consult-tools/local/claude/consult.local.md

# Windows (PowerShell)
Copy-Item ai-consult-tools\shared\consult.local.example.md ai-consult-tools\local\claude\consult.local.md
```

`consult.local.md` はGit管理外のため、コミットされません。スレッド開始時のinclude bundleに含めることで、AIがビルドコマンドを推測なく把握できます。

### 4. consult_case/ をGit管理外にする

生成物（バンドルMD）はAIへの一時的な添付物であり、Git管理不要です。`.gitignore` に追加することを推奨します。

```
ai-consult-tools/claude/consult_case/
ai-consult-tools/local/claude/consult.local.md
```

---

## 基本的な使い方

すべてのコマンドは対象プロジェクトのリポジトリルートで実行し、スクリプトは `ai-consult-tools/claude/consult_bundle_claude.py` を指定してください。

```bash
# map：リポジトリ全体の構造を把握する
python ai-consult-tools/claude/consult_bundle_claude.py --mode map --repo-root <your-repo>

# include：特定のファイル・フォルダを本文付きで出力する
python ai-consult-tools/claude/consult_bundle_claude.py --mode include --repo-root <your-repo> \
  --include-paths "src/controllers" "src/models"

# diff：修正後の変更内容をレビューする
python ai-consult-tools/claude/consult_bundle_claude.py --mode diff --repo-root <your-repo>

# repo：リポジトリ全体を本文付きで出力する（大規模リポジトリでは出力が大きくなる）
python ai-consult-tools/claude/consult_bundle_claude.py --mode repo --repo-root <your-repo>
```

引数の詳細は `01_make_consult_bundle_spec.md` を、相談フローの詳細は `03_claude_session_guide.md` を参照してください。

---

## 出力ファイルの場所

```
ai-consult-tools/claude/consult_case/<DocSet>_<Mode>[_<CaseName>].md
```

生成されたMDファイルをClaudeのチャットに添付するだけで、根拠確定した相談が始められます。

---

## 注意事項

- `secretNamePatterns` に一致するファイルは**自動的に除外**されます。ただし、設定が適切かどうかは必ず自分で確認してください。
- `consult.config.json` 自体に機密情報を書かないでください。
- 詳細は `shared/SECURITY.md` を参照してください。
