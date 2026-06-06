# ai-consult-tools

Claude・ChatGPT との開発相談を、**Git管理されたローカルリポジトリを根拠に行う**ためのツールセットです。

AIへの「推測による回答」を構造的に防ぎ、コードとドキュメントの実体を一次根拠とした相談フローを実現します。

---

## ツール構成

```
ai-consult-tools/
├── claude/     # Claude用ツール・運用ルール
└── chatgpt/    # ChatGPT用ツール・運用ルール
```

各フォルダに `README_release.md` があります。まずそちらをお読みください。

---

## 特徴

- **4モード対応**：map（軽量地図）/ include（範囲指定）/ diff（差分）/ repo（全体）
- **除外ルールをJSONで管理**：`.git`、`node_modules`、機密ファイル等を自動除外
- **単一MDファイルで出力**：AIに添付するだけで根拠確定できる構造
- **PowerShell 7+（pwsh）専用**：Windows環境で動作

---

## 動作要件

- **PowerShell 7+（pwsh）**
  - Windows PowerShell 5.1（`powershell.exe`）は非対応
  - インストール：https://learn.microsoft.com/ja-jp/powershell/scripting/install/installing-powershell-on-windows
- **Git**（リポジトリが `git init` 済みであること）

---

## セットアップ

### 1. ファイルを配置する

使用したいAIのフォルダ（`claude/` または `chatgpt/`）をリポジトリルート配下の任意の場所に配置してください。

推奨配置例：

```
your-repo/
└── ai-consult-tools/
    └── claude/         # または chatgpt/
        ├── make_consult_bundle.ps1
        ├── consult.config.json
        └── ...
```

### 2. 設定ファイルを作成する

`consult.config.example.json` をコピーして `consult.config.json` を作成し、環境に合わせて編集してください。

```powershell
Copy-Item claude\consult.config.example.json claude\consult.config.json
```

主な設定項目：

| キー | 説明 |
|---|---|
| `outRoot` | 生成物の出力先（リポジトリルートからの相対パス） |
| `excludeFolders` | 除外するフォルダのリスト |
| `secretNamePatterns` | 除外する機密ファイルのパターン |

### 3. consult_case/ をGit管理外にする

生成物はAIへの一時的な添付物のため、`.gitignore` に追加することを推奨します。

```
claude/consult_case/
chatgpt/consult_case/
```

---

## 基本的な使い方

すべてのコマンドは **リポジトリルートで実行**してください。

### map（構造把握）

```powershell
pwsh -File ai-consult-tools\claude\make_consult_bundle.ps1 -Mode map -RepoRoot "C:\your-repo"
```

### include（範囲指定）

```powershell
pwsh -File ai-consult-tools\claude\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\your-repo" -IncludePaths "src\controllers"
```

### diff（差分レビュー）

```powershell
pwsh -File ai-consult-tools\claude\make_consult_bundle.ps1 -Mode diff -RepoRoot "C:\your-repo"
```

生成された `.md` ファイルをAIのチャットに添付して相談を開始します。

---

## 基本的な相談フロー

```
map（構造把握）→ include（本文根拠の固定）→ 仕様案 → 合意 → 実装 → diff（レビュー）→ commit
```

詳細は各フォルダ内のドキュメントを参照してください。

- `README_release.md` — セットアップ・使い方の詳細
- `00_ai_consult_operation_rules.md` — AI相談の運用ルール
- `01_make_consult_bundle_spec.md` — スクリプト技術仕様
- `03_claude_session_guide.md` — セッション開始ガイド（Claude用）

---

## セキュリティ

機密ファイル（`.env*`、`*.pem`、`*.key` 等）は自動的に除外されます。詳細は `SECURITY.md` を参照してください。

---

## ライセンス

MIT License
