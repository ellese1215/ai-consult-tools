# 01 consult_bundle_chatgpt.py 技術仕様

> File: 01_make_consult_bundle_spec_chatgpt.md.

`consult_bundle_chatgpt.py` は、ローカルGitリポジトリから ChatGPT 相談用の参照 bundle を生成する Python スクリプトです。

---

## 1. 実行前提

コマンドは対象リポジトリルートから実行します。

```powershell
cd <your-repo>
```

スクリプトパスは以下を指定します。

```text
ai-consult-tools/chatgpt/consult_bundle_chatgpt.py
```

---

## 2. モード

```text
map      軽量なファイル一覧・構造確認
repo     リポジトリスナップショット
include  指定ファイル・指定フォルダの参照束
diff     Git差分ベースの参照束
```

---

## 3. 主要引数

```text
--mode                 map / repo / include / diff
--repo-root            対象リポジトリルート
--case-name            出力名に付ける任意の相談名
--config-path          設定ファイルの明示指定
--include-paths        include モードで含めるパス
--allow-docset-folders DocSetフォルダを明示的に許可
--keep-bundle-dir      ZIP作成後に _bundle を残す
--diag                 診断情報を出す
--staged               diff: staged差分
--unstaged-only        diff: unstaged差分のみ
--diff-base            diff: base ref
--diff-target          diff: target ref
```

---

## 4. 設定ファイル

デフォルト探索順は以下です。

```text
ai-consult-tools/local/chatgpt/consult.config_chatgpt.json
.consult/consult.config.json
```

`local/` は Git管理外です。ただし、相談時に明示 include するため、実設定側の `allowedToolIncludeFiles` には `local/` 配下の必要ファイルを含めます。

---

## 5. 基本コマンド

### map

```powershell
cd <your-repo>
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py --mode map --repo-root "<your-repo>" --case-name "map_check"
```

### repo

```powershell
cd <your-repo>
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py --mode repo --repo-root "<your-repo>" --case-name "repo_check"
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

---

## 6. 出力仕様

ChatGPT版は ZIP を生成します。

```text
ai-consult-tools/chatgpt/consult_case/<BundleLabel>/<BundleLabel>.zip
```

生成物は Git管理外です。

---

## 7. 除外と include 許可

`excludeFolders` / `excludeExtensions` / `secretNamePatterns` に該当するものは通常除外します。

ただし、`allowedToolIncludeFiles` に登録されたファイルは、相談ツール本体・設定・ローカル相談補助ファイルなどを明示 include するために使います。

`local/` は公開しませんが、以下は明示 include を許可します。

```text
ai-consult-tools/local/chatgpt/consult.config_chatgpt.json
ai-consult-tools/local/chatgpt/consult.local_chatgpt.md
```

---

## 8. diff モードの注意

`local/` は Git管理外です。そのため、通常の Git diff 由来の diff bundle には `local/` の変更は入りません。

これは仕様として許容します。必要な場合は include モードで明示的に含めます。
