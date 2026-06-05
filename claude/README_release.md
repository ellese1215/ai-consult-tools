# Claude相談ツール（make_consult_bundle）

Claude（またはその他のAI）との開発相談を、**Git管理されたローカルリポジトリを根拠に行う**ためのツールセットです。

AIへの「推測による回答」を構造的に防ぎ、コードとドキュメントの実体を一次根拠とした相談フローを実現します。

---

## 特徴

- **4モード対応**：map（軽量地図）/ include（範囲指定）/ diff（差分）/ repo（全体）
- **除外ルールをJSONで管理**：`.git`、`node_modules`、秘密情報ファイル等を自動除外
- **単一MDファイルで出力**：Claudeに添付するだけで根拠確定できる構造
- **secret patternによる情報漏洩防止**：`.env*`、`*.key`、`*.pem` 等を自動スキップ
- **PowerShell 7+（pwsh）専用**：Windows環境で動作

---

## ファイル構成

```
ai-consult-ai-consult-tools/claude/
├── make_consult_bundle.ps1       # バンドル生成スクリプト（本体）
├── consult.config.json           # 除外ルール等の設定（あなたの環境向けに編集）
├── consult.config.example.json   # 設定ファイルのテンプレート
├── 00_ai_consult_operation_rules.md  # Claude相談の運用ルール
├── 01_make_consult_bundle_spec.md    # スクリプト技術仕様
├── 02_consult_template.md            # スレッド開始テンプレート
├── 03_claude_session_guide.md        # セッション開始手順・モード選択ガイド
├── SECURITY.md                       # セキュリティ・取り扱い注意事項
└── consult_case/                     # 生成物の出力先（Git管理外推奨）
```

---

## 前提条件

- **PowerShell 7+（pwsh）** がインストールされていること
  - Windows PowerShell 5.1（`powershell.exe`）は非対応
  - インストール：https://learn.microsoft.com/ja-jp/powershell/scripting/install/installing-powershell-on-windows
- **Git** がインストールされていること
- 対象リポジトリが `git init` 済みであること（diff modeはコミット履歴が必要）

---

## セットアップ

### 1. ファイルを配置する

`ai-consult-ai-consult-tools/claude/` ディレクトリをリポジトリルート配下に配置してください。

```
your-repo/
└── tools/
    └── claude/
        ├── make_consult_bundle.ps1
        ├── consult.config.json   ← consult.config.example.json をコピーして編集
        └── ...
```

### 2. 設定ファイルを作成する

`consult.config.example.json` をコピーして `consult.config.json` を作成し、あなたの環境に合わせて編集してください。

```powershell
Copy-Item ai-consult-ai-consult-tools\claude\consult.config.example.json ai-consult-ai-consult-tools\claude\consult.config.json
```

主な設定項目：

| キー | 説明 |
|---|---|
| `outRoot` | 生成物の出力先（リポジトリルートからの相対パス） |
| `ruleFile` | 運用ルールファイルのパス |
| `excludeFolders` | 除外するフォルダ名のリスト |
| `excludeExtensions` | 除外する拡張子のリスト |
| `secretNamePatterns` | 除外するファイル名パターン（機密情報ファイル） |

詳細は `consult.config.example.json` のコメントおよび `SECURITY.md` を参照してください。

### 3. consult_case/ をGit管理外にする

生成物（バンドルMD）はAIへの一時的な添付物であり、Git管理不要です。`.gitignore` に追加することを推奨します。

```
ai-consult-ai-consult-tools/claude/consult_case/
```

---

## 使い方

すべてのコマンドは **リポジトリルートで実行**してください。

### Mode: map（軽量地図）

まず全体の構造を把握するために使います。本文は含まず、ファイル一覧・ツリーのみを出力します。

```powershell
pwsh -File ai-consult-ai-consult-tools\claude\make_consult_bundle.ps1 -Mode map -RepoRoot "C:\your-repo"
```

### Mode: include（範囲指定スナップショット）

特定のファイルやフォルダを指定して、本文付きで出力します。Claudeへの相談の主戦場です。

```powershell
# フォルダ指定
pwsh -File ai-consult-ai-consult-tools\claude\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\your-repo" -IncludePaths "src\controllers"

# 複数ファイル指定
pwsh -File ai-consult-ai-consult-tools\claude\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\your-repo" -IncludePaths "src\App.php","src\Config.php"
```

### Mode: diff（差分バンドル）

Gitの差分（HEAD vs 作業ツリー）を出力します。修正後のレビューに使います。

```powershell
# 未コミット差分（既定）
pwsh -File ai-consult-ai-consult-tools\claude\make_consult_bundle.ps1 -Mode diff -RepoRoot "C:\your-repo"

# staged差分
pwsh -File ai-consult-ai-consult-tools\claude\make_consult_bundle.ps1 -Mode diff -RepoRoot "C:\your-repo" -Staged

# コミット間差分
pwsh -File ai-consult-ai-consult-tools\claude\make_consult_bundle.ps1 -Mode diff -RepoRoot "C:\your-repo" -DiffBase HEAD~1 -DiffTarget HEAD
```

### Mode: repo（全体スナップショット）

リポジトリ全体を本文付きで出力します。大規模リポジトリでは出力が大きくなるため、通常はmap→includeを優先してください。

```powershell
pwsh -File ai-consult-ai-consult-tools\claude\make_consult_bundle.ps1 -Mode repo -RepoRoot "C:\your-repo"
```

### CaseName オプション（推奨）

生成物のファイル名に任意の識別名を付けられます。

```powershell
pwsh -File ai-consult-ai-consult-tools\claude\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\your-repo" -CaseName "login_feature" -IncludePaths "src\Auth"
# → consult_case/<DocSet>_include_login_feature.md
```

---

## 基本的な相談フロー

1. **map** でリポジトリ構造を把握 → Claudeに添付
2. Claudeに「どのファイルが必要か」を確認
3. **include** で必要なファイルを抽出 → Claudeに添付
4. Claudeと仕様・実装を相談・確定
5. ローカルで修正を適用
6. **diff** で変更内容をレビュー → Claudeに添付
7. 問題なければ commit → push

詳細は `03_claude_session_guide.md` を参照してください。

---

## 出力ファイルの場所

```
ai-consult-ai-consult-tools/claude/consult_case/<DocSet>_<Mode>[_<CaseName>].md
```

生成されたMDファイルをClaudeのチャットに添付するだけで、根拠確定した相談が始められます。

---

## 注意事項

- `secretNamePatterns` に一致するファイルは**自動的に除外**されます。ただし、設定が適切かどうかは必ず自分で確認してください。
- `consult.config.json` 自体に機密情報を書かないでください。
- 詳細は `SECURITY.md` を参照してください。
