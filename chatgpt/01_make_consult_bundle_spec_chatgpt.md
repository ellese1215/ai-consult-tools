# 01 consult_bundle_chatgpt.py 技術仕様

> File: 01_make_consult_bundle_spec_chatgpt.md
> Version: 1.7.0
> Updated: 2026-06-26

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
include  指定ファイル・指定フォルダ・include set の参照束
diff     Git差分ベースの参照束
```

---

## 3. 主要引数

```text
--mode                 map / repo / include / diff
--repo-root            対象リポジトリルート
--case-name            出力名に付ける任意の相談名
--config-path          設定ファイルの明示指定
--include-set          config の includeSets に定義した用途別セット名
--include-paths        include モードで含める個別パス
--allow-docset-folders DocSetフォルダを明示的に許可
--keep-bundle-dir      ZIP作成後に _bundle を残す
--diag                 診断情報を出す
--staged               diff: staged差分
--unstaged-only        diff: unstaged差分のみ
--diff-base            diff: base ref
--diff-target          diff: target ref
```

`--include-set` と `--include-paths` は併用できます。

---

## 4. 設定ファイル

デフォルト探索順は以下です。

```text
ai-consult-tools/local/chatgpt/consult.config_chatgpt.json
.consult/consult.config.json
```

`local/` は Git管理外です。ただし、相談時に明示 include するため、実設定側の `allowedToolIncludeFiles` には `local/` 配下の必要ファイルを含めます。

---

## 5. includeSets 仕様

`consult.config_chatgpt.json` に `includeSets` を定義できます。

```json
{
  "includeSets": {
    "common_rules": [
      "ai-consult-tools/shared/00_ai_consult_operation_rules.md",
      "ai-consult-tools/local/chatgpt/consult.local_chatgpt.md"
    ],
    "chatgpt_tool_core": [
      "ai-consult-tools/shared/00_ai_consult_operation_rules.md",
      "ai-consult-tools/local/chatgpt/consult.local_chatgpt.md",
      "ai-consult-tools/chatgpt/01_make_consult_bundle_spec_chatgpt.md",
      "ai-consult-tools/chatgpt/03_chatgpt_session_guide.md",
      "ai-consult-tools/chatgpt/consult_bundle_chatgpt.py"
    ]
  }
}
```

### 5.1 includeSets の目的

- よく使う include 対象をセット化する
- 毎回 `--include-paths` を長く手書きしない
- 相談ごとに添付されたりされなかったりするブレを防ぐ
- AIがパスを推測する場面を減らす

### 5.2 include set の解決ルール

- `--include-set <name>` は config の `includeSets.<name>` を展開する
- 複数の `--include-set` を指定できる
- `--include-set` と `--include-paths` を併用できる
- 存在しない include set 名はエラー停止する
- 展開後の重複パスは最終的に重複除去する
- 展開後の各パスは通常の include path と同じ除外ルールを通る

---

## 6. 基本コマンド

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

### include: include set

```powershell
cd <your-repo>
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py --mode include --repo-root "<your-repo>" --case-name "tool_core_check" --include-set "chatgpt_tool_core"
```

### include: include set + 個別パス

```powershell
cd <your-repo>
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py --mode include --repo-root "<your-repo>" --case-name "include_check" --include-set "common_rules" --include-paths "<対象ファイル>"
```

### diff

```powershell
cd <your-repo>
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py --mode diff --repo-root "<your-repo>" --case-name "diff_check"
```

---

## 7. 出力仕様

ChatGPT版は ZIP を生成します。

```text
ai-consult-tools/chatgpt/consult_case/<BundleLabel>/<BundleLabel>.zip
```

ZIP内には以下を含めます。

```text
00_ai_consult_operation_rules.md
INDEX.md
TREE.md
MANIFEST.csv
PATH_INDEX.md
SKIPPED.txt
parts/
```

`diff` モードでは上記に加えて `DIFF_INDEX.md` を含めます。

生成物は Git管理外です。

---

## 8. PATH_INDEX.md 仕様

`PATH_INDEX.md` は bundle 生成時に実ファイルから自動生成される索引です。手動更新ドキュメントではありません。

主な内容は以下です。

```text
- 使用した include set
- include set から展開されたパス
- --include-paths で直接指定したパス
- requested path ごとの解決結果
- missing / excluded / ambiguous の結果
- 最終的に bundle に含まれたファイル一覧
```

### 8.1 解決結果の分類

```text
ok         実在し、除外されず、bundle対象になった
missing    指定パスが存在しない、またはファイル名検索で見つからない
excluded   実在するが除外ルールに該当した
ambiguous  同名候補が複数あり、明示パスが必要
empty      空の指定
```

`PATH_INDEX.md` は、AIがパスを推測せず、bundle内の存在確認済み情報だけを根拠にするための確認資料です。

---

## 9. SKIPPED.txt 仕様

`SKIPPED.txt` には bundle に含めなかった対象を分類して出力します。

例：

```text
[missing] include-set:chatgpt_tool_core: ai-consult-tools/SECURITY.md
[excluded] include-paths: path/to/file.webp (excluded-extension)
[empty] include-paths:
```

`SKIPPED.txt` が `(none)` ではない場合、相談開始時に不足・除外が意図通りか確認します。

---

## 10. 除外と include 許可

`excludeFolders` / `excludeExtensions` / `excludeNamePatterns` / `secretNamePatterns` に該当するものは通常除外します。

ただし、`allowedToolIncludeFiles` に登録されたファイルは、相談ツール本体・設定・ローカル相談補助ファイルなどを明示 include するために使います。

`local/` は公開しませんが、以下は明示 include を許可します。

```text
ai-consult-tools/local/chatgpt/consult.config_chatgpt.json
ai-consult-tools/local/chatgpt/consult.local_chatgpt.md
```

`archive/` は通常相談の対象外とします。必要な場合だけ、明示的な include 対象として扱います。

---

## 11. diff モードの注意

`local/` は Git管理外です。そのため、通常の Git diff 由来の diff bundle には `local/` の変更は入りません。

これは仕様として許容します。必要な場合は include モードで明示的に含めます。
