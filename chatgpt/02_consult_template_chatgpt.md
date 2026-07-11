# 02 ChatGPT相談開始テンプレート

> **旧版資料**
>
> 本書はV4-6まで保持する旧モデル別スクリプト用資料です。現行共通CLIの正本ではありません。
> 現行の利用方法は`../README.md`、技術仕様は`../docs/01_current_spec.md`、運用ルールは`../shared/00_ai_consult_operation_rules.md`を参照してください。

> File: 02_consult_template_chatgpt.md.

ChatGPTに相談を開始するときは、まず参照 bundle を生成し、その bundle を唯一の正として扱います。

---

## 1. 基本 include

定型の相談では `--include-set` を優先します。

```powershell
cd <your-repo>
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py --mode include --repo-root "<your-repo>" --case-name "<相談名>" --include-set "common_rules" --include-paths "<対象ファイル>"
```

相談基盤の見直しでは次を使います。

```powershell
cd <your-repo>
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py --mode include --repo-root "<your-repo>" --case-name "consult_tools_review" --include-set "chatgpt_tool_core"
```

---

## 2. スレッド開始時に伝えること

```text
添付した bundle を唯一の正として参照してください。
shared/00_ai_consult_operation_rules.md に従ってください。
PATH_INDEX.md と SKIPPED.txt を確認し、含まれていないパスや除外されたパスを推測で補完しないでください。
不明点は推測せず、BlockingQuestions として提示してください。
```

---

## 3. bundle 種別

```text
map      まず構造だけ確認したい場合
include  対象ファイルを指定して相談する場合
diff     変更差分を相談する場合
repo     必要な場合のみリポジトリ全体を確認する場合
```

---

## 4. local/ の扱い

`local/` は公開しません。
ただし、相談時に必要な `consult.local_chatgpt.md` や `consult.config_chatgpt.json` は、`allowedToolIncludeFiles` と include set で明示的に bundle に含めます。

diff モードで Git管理外の `local/` が差分に出ない点は許容します。
