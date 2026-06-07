# 01 ChatGPT相談用スナップショット生成スクリプト仕様 v1.6.2

> File: 01_make_consult_bundle_spec.md.

## 1. 目的

`make_consult_bundle.ps1` は、ChatGPT相談で参照する根拠ファイルを ZIP として固定するためのツールです。

主目的は次の3点です。

```text
1. AIが推測で回答しないよう、参照元を固定する
2. map / repo / include / diff の相談束を同じ形式で作る
3. 生成物、秘密情報、大容量バイナリを consult.config.json で除外する
```

運用ルールそのものは `00_ai_consult_operation_rules.md` を正とします。この仕様書は、ツールの使い方と出力仕様を説明します。

## 2. 前提

PowerShell 7 以上で実行します。

Git差分を使う `diff` モードでは、対象ディレクトリが Git repo である必要があります。

v1.5.0 では、除外ルールと出力先を `consult.config.json` に集約します。ps1 内の固定除外リストに依存しません。

## 3. 配置

標準配置は次の通りです。

```text
ai-consult-tools/archive/chatgpt/make_consult_bundle.ps1
ai-consult-tools/local/chatgpt/consult.config_chatgpt.json
ai-consult-tools/chatgpt/consult.config.example_chatgpt.json
ai-consult-tools/shared/00_ai_consult_operation_rules.md
ai-consult-tools/chatgpt/01_make_consult_bundle_spec_chatgpt.md
```

`-ConfigPath` を省略した場合、設定ファイルは次の順に探索されます。

```text
1. ai-consult-tools/local/chatgpt/consult.config_chatgpt.json
2. .consult/consult.config.json
```

どちらも見つからない場合は停止します。

## 4. 引数

| 引数 | 必須 | 説明 |
|---|---:|---|
| `-Mode` | 必須 | `map` / `repo` / `include` / `diff` のいずれか |
| `-RepoRoot` | 必須 | 対象repoのルート |
| `-CaseName` | 任意 | 出力ZIP名に使う相談名 |
| `-IncludePaths` | include時のみ実質必須 | カンマ区切りの相対パス |
| `-ConfigPath` | 任意 | 使用する `consult.config.json` |
| `-Diag` | 任意 | diff が0件のときの診断出力 |
| `-MaxBytesPerPart` | 任意 | 1つの part ファイルに入れる目安バイト数。既定値は `536870912` |
| `-MaxCharsPerPart` | 任意 | 1つの part ファイルに入れる目安文字数。既定値は `300000` |
| `-MaxCharsPerFile` | 任意 | 1ファイル本文の切り詰め上限。既定値は `300000` |

## 5. consult.config.json

`consult.config.json` は v1.5.0 の設定の正です。

主な項目は次の通りです。

| 項目 | 説明 |
|---|---|
| `outRoot` | 相談束の出力先。RepoRoot からの相対パスを推奨 |
| `ruleFile` | ZIPに同梱する運用ルール文書 |
| `excludeFolders` | 除外するフォルダ |
| `excludeExtensions` | 除外する拡張子 |
| `excludeNamePatterns` | 除外するファイル名パターン |
| `secretNamePatterns` | 秘密情報として除外する名前パターン |
| `allowedToolIncludeFiles` | 除外配下でも例外的に含めるファイル |

`outRoot` と `ruleFile` は相対パスで書くことを推奨します。

## 6. モード概要

### 6.1 map モード

repoモードと同じ対象収集範囲から、本文全文を除いた軽量地図を作ります。include束に入れる候補ファイルを広めに拾うために使います。

```powershell
cd C:\xampp\htdocs; pwsh -NoProfile -ExecutionPolicy Bypass -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode map -RepoRoot "C:\xampp\htdocs" -CaseName "map_check"
```

ファイル一覧、ディレクトリ構造、Markdown見出し、PowerShell/PHP/TypeScriptのシンボル候補、SCSS selector候補、import/export候補などを確認し、IncludePaths候補を広めに拾うために使います。

map モードは本文根拠ではありません。map束だけを根拠に具体的なコード差分・仕様差分を作ってはいけません。また、map束だけで「関係なし」と確定除外しないでください。

### 6.2 repo モード

repo全体を横断確認するための本文付きスナップショットを作ります。

```powershell
cd C:\xampp\htdocs; pwsh -NoProfile -ExecutionPolicy Bypass -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode repo -RepoRoot "C:\xampp\htdocs" -CaseName "repo_check"
```

mapでは不足する場合の仕様確認、影響範囲確認、既存構造の把握に使います。

### 6.3 include モード

指定したファイルだけを束ねます。

```powershell
cd C:\xampp\htdocs; pwsh -NoProfile -ExecutionPolicy Bypass -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\xampp\htdocs" -CaseName "include_check" -IncludePaths "ai-consult-tools/shared/00_ai_consult_operation_rules.md,ai-consult-tools/archive/chatgpt/make_consult_bundle.ps1"
```

対象ファイルが明確な修正、軽量なレビュー、引き継ぎ用に使います。

### 6.4 diff モード

Git差分を ZIP にまとめます。

```powershell
cd C:\xampp\htdocs; pwsh -NoProfile -ExecutionPolicy Bypass -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode diff -RepoRoot "C:\xampp\htdocs" -CaseName "diff_check"
```

修正後のレビュー、コミット前確認に使います。

## 7. 除外規則

除外規則は `consult.config.json` に書きます。

公開用・相談用では、少なくとも次を除外対象にします。

```text
.git
node_modules
vendor
dist
build
out
release
coverage
ai-consult-tools/chatgpt/consult_case
ai-consult-tools/chatgpt/consult_project
.consult/consult_case
.consult/consult_project
```

バイナリや大容量ファイルは、拡張子で除外します。

```text
.zip
.7z
.rar
.png
.jpg
.jpeg
.webp
.gif
.mp3
.wav
.mp4
.pdf
.exe
.dll
.ttf
.otf
.woff
.woff2
```

秘密情報は名前パターンで除外します。

```text
.env*
*.env*
*secret*
*credential*
*.pem
*.key
*.pfx
*.p12
*.jks
*.keystore
id_rsa*
```

## 8. allowedToolIncludeFiles

`ai-consult-tools/chatgpt/consult_case` や `consult_project` は除外しますが、ツール本体や説明文書は相談対象にしたい場合があります。

その場合は `allowedToolIncludeFiles` に明示します。

```json
"allowedToolIncludeFiles": [
  "ai-consult-tools/archive/chatgpt/make_consult_bundle.ps1",
  "ai-consult-tools/shared/00_ai_consult_operation_rules.md",
  "ai-consult-tools/chatgpt/01_make_consult_bundle_spec_chatgpt.md",
  "ai-consult-tools/chatgpt/README_release_chatgpt.md",
  "ai-consult-tools/shared/SECURITY.md",
  "ai-consult-tools/local/chatgpt/consult.config_chatgpt.json",
  "ai-consult-tools/chatgpt/consult.config.example_chatgpt.json"
]
```

## 9. 出力物

生成ZIPには、主に次が入ります。

| ファイル | 説明 |
|---|---|
| `00_ai_consult_operation_rules.md` | 運用ルール文書 |
| `INDEX.md` | 参照確定情報、実行条件、統計 |
| `TREE.md` | 対象ファイルのツリー |
| `MANIFEST.csv` | 対象ファイル一覧 |
| `SKIPPED.txt` | スキップされたファイル |
| `parts/*.md` | ファイル内容のスナップショット、または map モードの軽量索引 |

AI相談では、まず `INDEX.md` と `00_ai_consult_operation_rules.md` を確認します。

## 10. INDEX.md の確認項目

`INDEX.md` では、最低限次を確認します。

```text
Mode
RepoRoot
ConfigPath
ConfigApplied
OutRoot
RuleFile
IncludedFiles
SkippedFiles
DocSet
GeneratedAt
CommandLine
```

`ConfigApplied: true` であること、意図した `ConfigPath` が使われていることを確認してください。

## 11. map モードの注意

map モードは repo と同じ対象収集範囲から、include へ受け渡す対象候補を広めに拾うための軽量地図です。

map モードでは実コード本文を原則出力しません。出力されるシンボル・見出し・selector・import/export候補は、IncludePaths候補を拾うための索引情報です。

具体的なコード差分・仕様差分を作る場合は、必ず include モードで対象ファイル本文を確認します。map の情報だけで不要ファイルを確定せず、迷うファイルは include 候補に含めます。

## 12. include モードの注意

`IncludePaths` は repo ルートからの相対パスで書きます。

```text
ai-consult-tools/archive/chatgpt/make_consult_bundle.ps1
docs/development/example.md
```

除外ルールに該当するファイルは include 指定してもスキップされます。必要なファイルは `allowedToolIncludeFiles` に追加します。

## 13. diff モードの注意

`diff` モードは Git差分を対象にします。

差分が0件の場合は、必要に応じて `-Diag` を付けて状態確認します。

```powershell
cd C:\xampp\htdocs; pwsh -NoProfile -ExecutionPolicy Bypass -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode diff -RepoRoot "C:\xampp\htdocs" -CaseName "diff_diag" -Diag
```

## 14. smoke test

default config 探索の確認です。

```powershell
cd C:\xampp\htdocs; pwsh -NoProfile -ExecutionPolicy Bypass -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode map -RepoRoot "C:\xampp\htdocs" -CaseName "public_v160_map_default_smoke"
```

従来の本文付き repo モード確認です。

```powershell
cd C:\xampp\htdocs; pwsh -NoProfile -ExecutionPolicy Bypass -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode repo -RepoRoot "C:\xampp\htdocs" -CaseName "public_v160_repo_default_smoke"
```

ConfigPath 明示の確認です。

```powershell
cd C:\xampp\htdocs; pwsh -NoProfile -ExecutionPolicy Bypass -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode map -RepoRoot "C:\xampp\htdocs" -ConfigPath "ai-consult-tools\local\chatgpt\consult.config_chatgpt.json" -CaseName "public_v160_map_config_smoke"
```

期待結果は、`.git/objects`、`cargo/common/webfonts`、生成済み `consult_case` が含まれず、warning が出ないことです。

## 15. 公開時の注意

公開用ZIPには、生成済み相談束、過去ログ、バックアップZIP、秘密情報、個人環境の絶対パスが濃いファイルを含めないでください。

詳細は `shared/SECURITY.md` を参照してください。
