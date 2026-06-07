# ai-consult-tools

Claude・ChatGPT との開発相談を、**Git管理されたローカルリポジトリを根拠に行う**ためのツールセットです。

AIへの「推測による回答」を構造的に防ぎ、コードとドキュメントの実体を一次根拠とした相談フローを実現します。

---

## ツール構成

```
ai-consult-tools/
├── shared/     # Claude / ChatGPT 共通ドキュメント
├── claude/     # Claude用スクリプト・ドキュメント
├── chatgpt/    # ChatGPT用スクリプト・ドキュメント
├── local/      # ローカル実設定（Git管理外）
│   ├── claude/
│   └── chatgpt/
└── archive/    # 退避物（Git管理外）
```

Claude版は `claude/README_release.md`、ChatGPT版は `chatgpt/README_release_chatgpt.md` をお読みください。

---

## 特徴

- **4モード対応**：map（軽量地図）/ include（範囲指定）/ diff（差分）/ repo（全体）
- **除外ルールをJSONで管理**：`.git`、`node_modules`、機密ファイル等を自動除外
- **Claude版はMDファイルで出力**：Claudeに添付するだけで根拠確定できる構造
- **ChatGPT版はZIPファイルで出力**：INDEX.md / TREE.md / MANIFEST.csv / partファイル群をZIPにまとめて添付
- **クロスプラットフォーム対応**：Windows / Mac / Linux で動作

---

## 動作要件

- **Python 3.9 以上**
  - 外部ライブラリ不要（標準ライブラリのみで動作）
- **Git**（リポジトリが `git init` 済みであること）

---

## セットアップ

### 1. ファイルを配置する

`ai-consult-tools/` ディレクトリを対象プロジェクトのリポジトリルート配下に配置してください。

```
your-repo/
└── ai-consult-tools/
    ├── shared/
    ├── claude/
    ├── chatgpt/
    ├── local/      # 初回セットアップで作成（Git管理外）
    └── archive/    # 退避物置き場（Git管理外）
```

### 2. 設定ファイルを作成する

使用するAIに応じて、公開テンプレートから `local/` 配下に実設定を作成してください。

**Claude版：**

```bash
# Mac / Linux
cp ai-consult-tools/claude/consult.config.example.json ai-consult-tools/local/claude/consult.config.json
cp ai-consult-tools/shared/consult.local.example.md ai-consult-tools/local/claude/consult.local.md

# Windows (PowerShell)
Copy-Item ai-consult-tools\claude\consult.config.example.json ai-consult-tools\local\claude\consult.config.json
Copy-Item ai-consult-tools\shared\consult.local.example.md ai-consult-tools\local\claude\consult.local.md
```

**ChatGPT版：**

```bash
# Mac / Linux
cp ai-consult-tools/chatgpt/consult.config.example_chatgpt.json ai-consult-tools/local/chatgpt/consult.config_chatgpt.json
cp ai-consult-tools/shared/consult.local.example.md ai-consult-tools/local/chatgpt/consult.local_chatgpt.md

# Windows (PowerShell)
Copy-Item ai-consult-tools\chatgpt\consult.config.example_chatgpt.json ai-consult-tools\local\chatgpt\consult.config_chatgpt.json
Copy-Item ai-consult-tools\shared\consult.local.example.md ai-consult-tools\local\chatgpt\consult.local_chatgpt.md
```

主な設定項目：

| キー | 説明 |
|---|---|
| `outRoot` | 生成物の出力先（リポジトリルートからの相対パス） |
| `ruleFile` | 運用ルールファイルのパス |
| `excludeFolders` | 除外するフォルダのリスト |
| `secretNamePatterns` | 除外する機密ファイルのパターン |

### 3. local/ と consult_case/ をGit管理外にする

`local/` と `archive/` はすでに `.gitignore` に登録済みです。
生成物（`consult_case/`）もGit管理外です。追加設定は不要です。

---

## 基本的な使い方

すべてのコマンドは **リポジトリルートで実行**してください。

### Claude版

```bash
# map：リポジトリ全体の構造を把握する
python ai-consult-tools/claude/consult_bundle_claude.py --mode map --repo-root <your-repo>

# include：特定のファイル・フォルダを本文付きで出力する
python ai-consult-tools/claude/consult_bundle_claude.py --mode include --repo-root <your-repo> \
  --include-paths "ai-consult-tools/shared/00_ai_consult_operation_rules.md" "src/controllers"

# diff：修正後の変更内容をレビューする
python ai-consult-tools/claude/consult_bundle_claude.py --mode diff --repo-root <your-repo>

# repo：リポジトリ全体を本文付きで出力する
python ai-consult-tools/claude/consult_bundle_claude.py --mode repo --repo-root <your-repo>
```

### ChatGPT版

```bash
# map
python ai-consult-tools/chatgpt/consult_bundle_chatgpt.py --mode map --repo-root <your-repo>

# include
python ai-consult-tools/chatgpt/consult_bundle_chatgpt.py --mode include --repo-root <your-repo> \
  --include-paths "ai-consult-tools/shared/00_ai_consult_operation_rules.md" "src/controllers"

# diff
python ai-consult-tools/chatgpt/consult_bundle_chatgpt.py --mode diff --repo-root <your-repo>

# repo
python ai-consult-tools/chatgpt/consult_bundle_chatgpt.py --mode repo --repo-root <your-repo>
```

生成された `.md`（Claude版）または `.zip`（ChatGPT版）をAIのチャットに添付して相談を開始します。

---

## 基本的な相談フロー

```
map（構造把握）→ include（本文根拠の固定）→ 仕様案 → 合意 → 実装 → diff（レビュー）→ commit
```

詳細は各フォルダ内のドキュメントを参照してください。

- `claude/README_release.md` — Claude版セットアップ・使い方の詳細
- `chatgpt/README_release_chatgpt.md` — ChatGPT版セットアップ・使い方の詳細
- `shared/00_ai_consult_operation_rules.md` — AI相談の運用ルール（Claude / ChatGPT 共通）
- `claude/01_make_consult_bundle_spec.md` — Claude版スクリプト技術仕様
- `chatgpt/01_make_consult_bundle_spec_chatgpt.md` — ChatGPT版スクリプト技術仕様
- `claude/03_claude_session_guide.md` — セッション開始ガイド（Claude用）

---

## セキュリティ

機密ファイル（`.env*`、`*.pem`、`*.key` 等）は自動的に除外されます。詳細は `shared/SECURITY.md` を参照してください。

---

## ライセンス

MIT License
