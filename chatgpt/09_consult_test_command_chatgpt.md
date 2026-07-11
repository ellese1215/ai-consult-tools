# 09 ChatGPT相談ツール テストコマンド

> **旧版資料**
>
> 本書はV4-6まで保持する旧モデル別スクリプト用資料です。現行共通CLIの正本ではありません。
> 現行の利用方法は`../README.md`、技術仕様は`../docs/01_current_spec.md`、運用ルールは`../shared/00_ai_consult_operation_rules.md`を参照してください。

> File: 09_consult_test_command_chatgpt.md.

すべてリポジトリルート（`<your-repo>`）から実行します。

---

## 1. map

```powershell
cd <your-repo>
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py --mode map --repo-root "<your-repo>" --case-name "test_map"
```

---

## 2. include: local 設定確認

```powershell
cd <your-repo>
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py --mode include --repo-root "<your-repo>" --case-name "test_include_local" --include-paths "ai-consult-tools/local/chatgpt/consult.config_chatgpt.json" "ai-consult-tools/local/chatgpt/consult.local_chatgpt.md"
```

---

## 3. include: 共有ルール確認

```powershell
cd <your-repo>
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py --mode include --repo-root "<your-repo>" --case-name "test_include_rules" --include-paths "ai-consult-tools/shared/00_ai_consult_operation_rules.md" "ai-consult-tools/shared/SECURITY.md" "ai-consult-tools/shared/consult.local.example.md"
```

---

## 4. diff

```powershell
cd <your-repo>
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py --mode diff --repo-root "<your-repo>" --case-name "test_diff"
```

### staged差分

```powershell
cd <your-repo>
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py --mode diff --repo-root "<your-repo>" --staged --case-name "test_diff_staged"
```

### unstaged差分

```powershell
cd <your-repo>
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py --mode diff --repo-root "<your-repo>" --unstaged-only --case-name "test_diff_unstaged"
```

---

## 5. repo

```powershell
cd <your-repo>
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py --mode repo --repo-root "<your-repo>" --case-name "test_repo"
```

---

## 6. 診断

```powershell
cd <your-repo>
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py --mode map --repo-root "<your-repo>" --diag --case-name "test_diag"
```

---

## 7. 確認

```powershell
cd <your-repo>\ai-consult-tools
git status --short --untracked-files=all
```

`consult_case/`、`local/`、`archive/` は Git管理外のため、通常は表示されません。
