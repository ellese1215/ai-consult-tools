# 02 ChatGPT相談開始テンプレート

> File: 02_consult_template_chatgpt.md.

ChatGPTに相談を開始するときは、まず参照 bundle を生成し、その bundle を唯一の正として扱います。

---

## 1. 基本 include

```powershell
cd <your-repo>
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py --mode include --repo-root "<your-repo>" --case-name "<相談名>" --include-paths "ai-consult-tools/shared/00_ai_consult_operation_rules.md" "ai-consult-tools/local/chatgpt/consult.local_chatgpt.md" "<対象ファイル>"
```

---

## 2. スレッド開始時に伝えること

```text
添付した bundle を唯一の正として参照してください。
shared/00_ai_consult_operation_rules.md に従ってください。
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
ただし、相談時に必要な `consult.local_chatgpt.md` や `consult.config_chatgpt.json` は、明示 include で bundle に含めます。

diff モードで Git管理外の `local/` が差分に出ない点は許容します。
