# ChatGPT相談ツール（consult_bundle_chatgpt）

> File: README_release_chatgpt.md.

このディレクトリは、ChatGPT相談用の bundle 生成ツールと、ChatGPT専用ドキュメントを管理します。

PowerShell版 `make_consult_bundle.ps1` は廃止済みです。現在の実行単位は Python スクリプトです。

---

## 1. 配置

```text
ai-consult-tools/
├── shared/
│   ├── 00_ai_consult_operation_rules.md
│   ├── SECURITY.md
│   └── consult.local.example.md
├── chatgpt/
│   ├── consult_bundle_chatgpt.py
│   ├── consult.config.example_chatgpt.json
│   ├── 01_make_consult_bundle_spec_chatgpt.md
│   ├── 02_consult_template_chatgpt.md
│   ├── 09_consult_test_command_chatgpt.md
│   ├── README_release_chatgpt.md
│   └── consult_case/
├── local/
│   └── chatgpt/
│       ├── consult.config_chatgpt.json
│       └── consult.local_chatgpt.md
└── archive/
    └── chatgpt/
        ├── consult_bundle_chatgpt.zip
        └── make_consult_bundle.ps1
```

`local/` と `archive/` は Git管理外です。公開リポジトリには含めません。

---

## 2. 初期設定

公開用テンプレートから、Git管理外の実設定を作成します。

まず `local/chatgpt/` ディレクトリを作成します。

```powershell
cd <your-repo>
New-Item -ItemType Directory -Force -Path ai-consult-tools\local\chatgpt
```

次に設定ファイルをコピーします。

```powershell
cd <your-repo>
Copy-Item .\ai-consult-tools\chatgpt\consult.config.example_chatgpt.json .\ai-consult-tools\local\chatgpt\consult.config_chatgpt.json
Copy-Item .\ai-consult-tools\shared\consult.local.example.md .\ai-consult-tools\local\chatgpt\consult.local_chatgpt.md
```

実設定ファイルは公開しません。ただし、相談時に必要であれば明示 include できます。

---

## 3. 基本コマンド

すべてリポジトリルート（`<your-repo>`）から実行します。

### map

```powershell
cd <your-repo>
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py --mode map --repo-root "<your-repo>" --case-name "map_check"
```

### include

```powershell
cd <your-repo>
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py --mode include --repo-root "<your-repo>" --case-name "include_check" --include-paths "ai-consult-tools/shared/00_ai_consult_operation_rules.md" "ai-consult-tools/local/chatgpt/consult.local_chatgpt.md"
```

### diff

```powershell
cd <your-repo>
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py --mode diff --repo-root "<your-repo>" --case-name "diff_check"
```

### repo

```powershell
cd <your-repo>
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py --mode repo --repo-root "<your-repo>" --case-name "repo_check"
```

---

## 4. 設定ファイル探索順

`--config-path` を省略した場合、以下を順に探索します。

```text
ai-consult-tools/local/chatgpt/consult.config_chatgpt.json
.consult/consult.config.json
```

明示する場合は以下です。

```powershell
cd <your-repo>
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py --mode include --repo-root "<your-repo>" --config-path "ai-consult-tools/local/chatgpt/consult.config_chatgpt.json" --case-name "config_check" --include-paths "ai-consult-tools/local/chatgpt/consult.config_chatgpt.json" "ai-consult-tools/local/chatgpt/consult.local_chatgpt.md"
```

---

## 5. 出力

ChatGPT版は ZIP を生成します。

```text
ai-consult-tools/chatgpt/consult_case/<DocSet>_<Mode>[_<CaseName>]/
└── <DocSet>_<Mode>[_<CaseName>].zip
```

`consult_case/` は Git管理外です。

---

## 6. セキュリティ

詳細は `shared/SECURITY.md` を参照してください。

`local/` は公開しません。ただし、相談時に必要な `consult.config_chatgpt.json` と `consult.local_chatgpt.md` は、明示 include により bundle に含める運用を許可します。
