# AI相談運用基盤 現行技術仕様

> File: `docs/01_current_spec.md`
> Updated: 2026-07-24

## 1. この文書の役割

本書は、AI相談運用基盤の共通CLI、設定、構造管理、bundle、物理出力の現行技術仕様を定義する。

文書の役割は以下のように分離する。

| 文書 | 役割 |
|---|---|
| `README.md` | 公開入口、導入、基本的な利用方法 |
| `shared/00_ai_consult_operation_rules.md` | 役割と必須ゲートの最上位契約 |
| `shared/01_ai_consult_procedures.md` | bundleと工程受渡しの詳細手順 |
| `shared/02_consult_template.md` | 共通工程状態と依頼テンプレート |
| `docs/handoff/current.md` | AI相談ツール保守の現在工程状態 |
| 本書 | 現行技術仕様 |
| `shared/SECURITY.md` | 除外、機密情報、生成物の取扱い |
| `local/consult.local.md` | 個別環境のローカル情報 |

実装と自動試験は現行動作の検証根拠である。旧スクリプトのファイルパスは第11章の互換入口として現行契約に含む。

## 2. 動作要件と入口

### 2.1 動作要件

- Python 3.10以上
- Git管理されたリポジトリ
- 外部Pythonパッケージ不要

### 2.2 実行入口

RepoRootで以下を実行する。

```text
python ai-consult-tools/consult.py <command> [options]
```

`consult.py`は`ai-consult-tools/src`をPythonパスへ追加し、`ai_consult.cli.main`を呼び出す。

`--repo-root`を省略した場合は`ai-consult-tools`の親ディレクトリ、指定した場合はそのパスをRepoRootとし、設定、プロファイル、対象パス、出力先をすべてRepoRoot境界内で解決する。

## 3. CLI

現行CLIは`find`、`structure sync`、`structure check`、`start`、`review`の5系統である。

旧版の`map`、`include`、`diff`、`repo`は現行共通CLIのコマンドではない。

### 3.1 共通オプション

| オプション | 対象 | 内容 |
|---|---|---|
| `--repo-root <path>` | 全コマンド | RepoRootを指定 |
| `--config-path <path>` | 全コマンド | RepoRoot相対の共通設定を明示指定 |
| `--target chatgpt|claude` | `start`、`review` | 物理出力形式を選択。必須 |
| `--profile <name>` | `start`、`review` | 対象プロジェクトを選択。必須 |
| `--case-name <name>` | `start`、`review` | 成果物名へ付加する任意名 |

`find --profile`は任意であり、検索範囲を対象プロジェクトへ限定する。

### 3.2 `find`

```text
python ai-consult-tools/consult.py find <query>
python ai-consult-tools/consult.py find <query> --profile <name>
```

ローカル構造インデックスをread-onlyで検索し、実行前に現在構造と比較する。インデックスが未生成、古い、形式不正の場合は更新せず、`structure sync`を案内して終了する。

大文字小文字を区別せず、`\`を`/`へ正規化し、先頭`./`と末尾`/`を除去する。完全相対パス、完全ファイル名、ファイル名部分一致、部分パス一致の順で優先し、同順位は決定的なパス順で全候補を表示する。

終了コードは、一致ありが0、一致なしが1、処理エラーが2である。

### 3.3 `structure sync`

```text
python ai-consult-tools/consult.py structure sync
```

現在構造を1回走査し、同一snapshotから`folder_tree.txt`とローカル構造インデックスを生成する。内容が変わったファイルだけを更新し、追加、削除、移動候補を表示する。両方最新なら`current`、どちらかを更新した場合は`updated`を表示する。

生成先は以下である。

```text
folder_tree.txt
ai-consult-tools/local/cache/repo_structure_index.json
```

### 3.4 `structure check`

```text
python ai-consult-tools/consult.py structure check
```

現在構造と`folder_tree.txt`、ローカル構造インデックスを比較し、ファイルとディレクトリは変更しない。両方最新なら終了コード0、未生成、古い、形式不正なら1、走査・読込エラーなら2を返す。

終了コード1は構造資料の診断結果であり、`start`が実行不能であることを示さない。`structure check`をstartの必須前処理または停止条件にしてはならない。

### 3.5 `start`

```text
python ai-consult-tools/consult.py start \
  --target <chatgpt|claude> \
  --profile <name> \
  [--case-name <name>] \
  [--include-set <name>]... \
  [--include-paths <path>...]
```

- 対象プロジェクトの開始用bundleを生成する
- `--include-set`は複数回指定でき、設定済みの共通資料をプロファイル外からも収集できる
- 通常の引き継ぎは`--include-set common_rules`で最上位契約、共通工程テンプレート、ローカル運用情報を収録する
- AI相談ツール保守は`--include-set ai_consult_maintenance`でREADME、現行仕様、詳細手順、SECURITY、local文書例を追加する
- `--include-paths`はRepoRoot相対かつ選択プロファイル内の明示対象だけを指定できる
- bundle収集前に現在構造を1回走査する
- 永続`folder_tree.txt`とローカル構造インデックスを作成、修復、更新しない
- 永続構造資料が`current`、`stale`、`missing`、`invalid`のいずれでも生成を継続する
- 同一live inventory snapshotから`generated`由来の`folder_tree.txt`と構造生成文書をbundle内生成する
- 永続構造資料の開始時状態、取得可能な`folder_tree.txt`のprofile内差分、startが永続資料を変更していない事実を`STRUCTURE_STATUS.md`へ記録する
- `PROJECT_TREE.md`には選択プロファイルの`scopeRoots`だけを収録する
- 明示対象の解決結果、除外、不足、失敗を`PATH_INDEX.md`と`SKIPPED.md`へ記録する
- 外部wrapperによる事前の`structure check`、一時設定生成、ZIP内部の重複検証を標準契約に含めない

### 3.6 `review`

```text
python ai-consult-tools/consult.py review \
  --target <chatgpt|claude> \
  --profile <name> \
  [--case-name <name>] \
  [--target-paths <path>...]
```

- 対象プロジェクト内のstaged、unstaged、未追跡を区別して収集する
- `--target-paths`でレビュー対象をRepoRoot相対パスへ限定できる
- ignore対象ファイルは完全なファイルパスを明示した場合だけ未追跡項目として収録し、ignore対象ディレクトリを再帰展開しない
- 各明示対象は収録項目または`SKIPPED.md`へ記録し、変更なしは`no_changes`、不存在かつGit変更なしは`missing`とする
- renameは現在パスと`previous_path`を保持する
- 変更もskipもない場合は成果物を作らず`review: no changes`で終了する
- 収録項目がなくてもskipが存在する場合は成果物を生成する

## 4. 共通設定

### 4.1 読込順

1. `--config-path`が指定された場合は、そのRepoRoot相対ファイルを読む
2. 未指定で`ai-consult-tools/local/consult.config.json`が存在する場合は、それを読む
3. どちらもない場合は`{"schemaVersion": 1}`相当の既定値を使用する

設定JSONはUTF-8またはUTF-8 BOM付きで読み込む。

未知のキー、未対応`schemaVersion`、不正な型、非正規パスはエラーとする。

### 4.2 スキーマ

```json
{
  "schemaVersion": 1,
  "filters": {
    "excludePaths": [],
    "binaryExtensions": [],
    "maxTextBytes": 2000000
  },
  "inventory": {
    "excludePaths": []
  },
  "includeSets": {
    "common_rules": [
      "ai-consult-tools/shared/00_ai_consult_operation_rules.md",
      "ai-consult-tools/shared/02_consult_template.md",
      "ai-consult-tools/local/consult.local.md"
    ],
    "ai_consult_maintenance": [
      "ai-consult-tools/README.md",
      "ai-consult-tools/docs/01_current_spec.md",
      "ai-consult-tools/shared/01_ai_consult_procedures.md",
      "ai-consult-tools/shared/SECURITY.md",
      "ai-consult-tools/shared/consult.local.example.md"
    ],
    "repository_structure": [
      "docs/REPOSITORY_STRUCTURE.md"
    ]
  },
  "outputs": {
    "chatgpt": {
      "outRoot": "ai-consult-tools/chatgpt/consult_case",
      "maxBytesPerPart": 536870912,
      "maxCharsPerPart": 300000
    },
    "claude": {
      "outRoot": "ai-consult-tools/claude/consult_case",
      "maxCharsPerPart": 300000
    }
  }
}
```

### 4.3 設定項目

| キー | 内容 |
|---|---|
| `filters.excludePaths` | 本文収集から追加除外するパス規則 |
| `filters.binaryExtensions` | バイナリとして扱う追加拡張子 |
| `filters.maxTextBytes` | 1ファイルの本文収集上限 |
| `inventory.excludePaths` | 構造走査の既定除外へ追加するパス規則 |
| `includeSets` | `start --include-set`で使う名前付きパス集合 |
| `outputs.chatgpt` | ChatGPT出力先とpart上限 |
| `outputs.claude` | Claude出力先とpart上限 |

`inventory.excludePaths`は組み込みの構造除外規則へ追加される。ローカル設定やconsult生成物、`.git`、主要build生成物、代表的な機密名は組み込み既定で構造走査から除外する。

実際に設定された`outputs.chatgpt.outRoot`と`outputs.claude.outRoot`は生成物専用領域である。設定読込時の正規化済みRepoRoot相対パスを、globではなくリテラルなディレクトリ境界として保持する。`[`、空白、Unicodeなどをglobメタ文字へ変換せず、outRootとの完全一致または`/`境界の子孫だけを大文字小文字を区別しない既存方針で判定する。兄弟や単なる前方一致は除外せず、duplicate／nested設定も同じ判定へ収束する。

両outRootは現在のtarget、tracked／untracked、staged／unstaged、拡張子を問わず、live inventory、collection、Git差分候補、folder tree、構造index、`PROJECT_TREE.md`、`PATH_INDEX.md`、`STRUCTURE_STATUS.md`のパス列挙、bundle item、`MANIFEST.csv`、`SKIPPED.md`から列挙・読込・hash計算前に無言で完全除外する。自動outRoot除外は一般の`filters.excludePaths`／`inventory.excludePaths`へ追加せず、一般除外の理由記録と`SkippedItem`契約を維持したまま別経路で扱う。

`start --include-paths`、include set、`review --target-paths`でoutRoot自体または子孫を明示指定した場合は、正式成果物を作成せずエラー終了する。outRoot外の正規ソースはリポジトリ相対パス、本文、`MANIFEST.csv` item、part見出し、構造資料のパスを維持する。ソース文書が設定項目`outRoot`を説明していても本文を伏字化しない。

CLIが現在の実行で新規生成した成果物を通知する`output:`と、ChatGPTの`bundle_path:`、`bundle_sha256:`、`sidecar_path:`、`sidecar_match:`は収集除外の例外として端末出力へ維持するが、後続bundleへ継承しない。既存bundle、ZIP、sidecar、Claude Markdown、一時成果物は削除、移動、上書きしない。

設定内のパスはRepoRoot相対、`/`区切り、`.`と`..`を含まない正規形とする。

標準設定の`common_rules`は通常引き継ぎ用の3文書、`ai_consult_maintenance`はツール保守用の5文書である。各構成ファイルを`--include-paths`へ重複指定せず、案件の`handoff/current.md`と必要資料は別途指定する。

## 5. プロジェクトプロファイル

### 5.1 読込順

1. `ai-consult-tools/local/project_profiles.json`が存在する場合はそれを使用する
2. 存在しない場合は`ai-consult-tools/config/project_profiles.example.json`を使用する

`start`と`review`ではプロファイル指定が必須である。`find`では任意である。

### 5.2 スキーマ

```json
{
  "schemaVersion": 1,
  "profiles": {
    "ai_consult_tools": {
      "scopeRoots": [
        "ai-consult-tools"
      ]
    }
  }
}
```

`scopeRoots`はRepoRoot相対、`/`区切り、末尾`/`なしとする。空文字、絶対パス、`.`、`..`、同一プロファイル内の重複を拒否する。

対象パスが`scopeRoot`と一致するか、`scopeRoot + "/"`で始まる場合にプロファイル所属と判定する。

`start`では、任意指定の`--include-paths`にこの所属判定を適用する。設定管理された`--include-set`は共通資料を複数プロファイルで共有するため所属判定をまたげるが、RepoRoot外のパスやリンク先は従来どおり拒否する。構造生成文書の対象は常に選択プロファイルの`scopeRoots`だけとする。

## 6. 構造管理

### 6.1 `folder_tree.txt`

- RepoRoot内のパスを確認するための補助資料
- UTF-8 BOMなし
- LF
- RepoRoot相対
- `/`区切り
- フォルダとファイルのパスだけを収録
- 決定的ソート
- 構造が変わった場合だけ更新
- 手動編集禁止
- 永続ファイルを更新するのは`structure sync`だけ
- `start`は永続ファイルを変更せず、live inventory snapshotから同名itemをbundle内生成する
- 手動のinclude指定は不要
- 永続ファイルの鮮度、存在、形式は`STRUCTURE_STATUS.md`へ報告するが、bundle生成の停止条件にしない
- 既存の永続ファイルは`start`前後でbyte-identicalに維持する

### 6.2 ローカル構造インデックス

生成先は以下である。

```text
ai-consult-tools/local/cache/repo_structure_index.json
```

- Git管理しない
- UTF-8 BOMなし
- LF
- 2スペースインデント
- 末尾LFあり
- 生成日時と絶対RepoRootを収録しない
- `entries`は構造走査と同じ決定的順序

永続インデックスを作成または更新するのは`structure sync`だけである。`start`は親ディレクトリを含めて作成せず、既存インデックスを変更しない。`structure check`は比較だけ、`find`はcurrentなインデックスの読取りだけを担当する。

構造走査では画像、音声、フォント、ZIPなどもパスとして記録できる。本文収集は判定済みテキストだけを対象とする。

symlinkとjunctionはパスを記録できるが、リンク先へ再帰しない。

## 7. 共通bundle契約

### 7.1 成果物名

DocSetは生成時刻のJSTを`YYYYMMDDhhmmss`で表した14桁である。

```text
<DocSet>_start[_<CaseName>]
<DocSet>_review[_<CaseName>]
```

`case-name`は前後空白を除去し、空白列を`_`へ変換した後、ASCII英数字、`.`、`_`、`-`以外を除去する。結果が空ならエラーとする。

### 7.2 共通生成テキスト

共通生成テキストはUTF-8 BOMなし、LF、末尾LFありとする。

### 7.3 manifest

`MANIFEST.csv`は以下の8列を固定順で使用する。

```text
relative_path
content_kind
origin
git_change
previous_path
source_bytes
source_sha256
encoding
```

本文ブロックも同じ由来情報を保持する。

```text
Path
ContentKind
Origin
GitChange
PreviousPath
Encoding
SourceBytes
SourceSHA256
```

### 7.4 `start`生成文書

```text
INDEX.md
REPO_OVERVIEW.md
PROJECT_TREE.md
STRUCTURE_STATUS.md
PATH_INDEX.md
SKIPPED.md
MANIFEST.csv
```

| 文書 | 役割 |
|---|---|
| `INDEX.md` | DocSet、command、target、profile、出力一覧、件数 |
| `REPO_OVERVIEW.md` | 主要ルートと対象プロジェクト配置 |
| `PROJECT_TREE.md` | 対象プロジェクトの最新パスツリー |
| `STRUCTURE_STATUS.md` | 構造正本との比較結果 |
| `PATH_INDEX.md` | include要求と解決結果 |
| `SKIPPED.md` | 除外、不足、失敗理由 |
| `MANIFEST.csv` | 収録項目一覧 |

live inventory snapshotから生成した`folder_tree.txt`は、上記固定文書とは別の通常content itemとして`parts/snapshot_docs_part_<NNN>.md`へ収録し、`MANIFEST.csv`では`origin=generated`として記録する。永続`folder_tree.txt`の内容を更新または再読込して生成しない。

### 7.5 `review`生成文書

```text
INDEX.md
DIFF_INDEX.md
SKIPPED.md
MANIFEST.csv
```

`DIFF_INDEX.md`はstaged、unstaged、未追跡の件数と各項目を記録する。

### 7.6 出力確定

- 一時ディレクトリ内で出力を完成させる
- 完成後に最終成果物ディレクトリへrenameする
- 失敗時は一時ディレクトリを削除する
- 一時ディレクトリ名はBundleLabelを含まない短い固定prefixを使用する
- 同名の最終成果物が存在する場合は上書きせずエラーとする
- 出力先はRepoRoot内でなければならない

## 8. ChatGPT出力

### 8.1 配置

既定出力先は以下である。

```text
ai-consult-tools/chatgpt/consult_case/<BundleLabel>/<BundleLabel>.zip
ai-consult-tools/chatgpt/consult_case/<BundleLabel>/<BundleLabel>.zip.sha256
```

ZIPと`.zip.sha256`の2点がstartとreviewの正式成果物である。sidecarはUTF-8 BOMなしで、次の1行と末尾CRLF 1件だけを持つ。

```text
<64桁の大文字SHA-256> *<ZIPのbasename><CRLF>
```

sidecarへ絶対パスやZIP以外を記録しない。ZIPのentry検証、ZIP hash計算、sidecar生成、sidecarと同一ディレクトリのZIPとの照合を一時ディレクトリ内で完了してから、成果物ディレクトリを確定する。失敗時はZIPだけ、sidecarだけ、古いhash、一時成果物、最終bundleディレクトリのいずれも残さない。

### 8.2 ZIP構造

`start`では以下の順でZIPへ格納する。

```text
INDEX.md
REPO_OVERVIEW.md
PROJECT_TREE.md
STRUCTURE_STATUS.md
PATH_INDEX.md
SKIPPED.md
MANIFEST.csv
parts/...
```

`review`では以下の順で格納する。

```text
INDEX.md
DIFF_INDEX.md
SKIPPED.md
MANIFEST.csv
parts/...
```

part名は以下である。

```text
parts/snapshot_<group>_part_<NNN>.md
parts/diff_<group>_part_<NNN>.md
```

`group`は`config`、`docs`、`js`、`misc`、`php`、`sql`、`styles`、`ts`のいずれかである。

### 8.3 決定性

- ZIP entry順を固定する
- timestampを1980-01-01 00:00:00へ固定する
- permissionを通常ファイル`0644`へ固定する
- ZIP作成後にentry順と破損を検証する
- 同一入力と同一出力コンテキストから同一バイト列を生成する

part上限は文字数とUTF-8バイト数の両方で判定する。1つのbundle itemを途中分割せず、item境界でpartを分ける。

### 8.4 CLI成功出力

ZIPとsidecarの生成・検証・最終配置が完了した場合だけ終了コード0と`start: created`または`review: created`を返す。従来の`target:`、`bundle:`、各`output:`に加えて次を固定行として出力する。

```text
bundle_path: <ZIP絶対パス>
bundle_sha256: <64桁の大文字SHA-256>
sidecar_path: <sidecar絶対パス>
sidecar_match: true
```

通常wrapperはBundleLabelや成果物名を推測せず、このCLI出力を解析する。Claudeはsidecar対象外であり、この4行を追加しない。

## 9. Claude出力

### 9.1 配置

既定出力先は以下である。

```text
ai-consult-tools/claude/consult_case/<BundleLabel>/
```

1partの場合：

```text
<BundleLabel>.md
```

複数partの場合：

```text
<BundleLabel>_part1.md
<BundleLabel>_part2.md
...
```

### 9.2 内容

最初のpartには以下を順に含める。

```text
参照確定情報
INDEX
start生成文書またはDIFF_INDEX・SKIPPED
MANIFEST
CONTENT
```

続きのpartにはDocSet、command、targetを含む継続ヘッダーを付ける。

INDEXには実際に生成されたpart名を記録し、未置換placeholderを残さない。

part上限は文字数で判定する。1つのbundle itemを途中分割せず、item境界でpartを分ける。

## 10. エラーと終了コード

| 終了コード | 意味 |
|---:|---|
| 0 | 成功、最新、一致あり、またはレビュー変更なし |
| 1 | 構造が古い、または検索一致なし |
| 2 | 設定、パス、収集、Git、出力などの処理エラー |

処理エラーは標準エラーへ`ERROR: <message>`を出力する。

主なエラー条件は以下である。

- 未対応または不正な設定
- 未知のプロファイル、include set
- RepoRoot外または非正規パス
- 古い・不正な構造インデックスでの`find`
- 必須生成文書の不足・重複
- 出力先がRepoRoot外
- 同名成果物の存在
- ZIPまたはMarkdown生成・検証失敗

## 11. 旧版互換入口

旧ファイルパスは薄い互換ラッパーとして維持し、収集、Git差分、bundle生成を現行共通CLIへ委譲する。

```text
ai-consult-tools/chatgpt/consult_bundle_chatgpt.py
ai-consult-tools/claude/consult_bundle_claude.py
```

ChatGPT版は`--target chatgpt`、Claude版は`--target claude`へ固定する。利用者による`--target`指定は受理しない。両入口とも`--repo-root`と`--profile`を必須とする。
実行時は標準エラーへ警告を表示する。

```text
WARNING: legacy entry point; use ai-consult-tools/consult.py for new commands.
```

| 旧モード | 変換先 | 収集範囲 |
|---|---|---|
| `map` | `start` | 明示ファイルを加えず、現行の構造生成文書だけ |
| `repo` | `start` | 選択profileの`scopeRoots` |
| `include` | `start` | `--include-set`と`--include-paths`の明示対象 |
| `diff` | `review` | 現行契約のstaged、unstaged、未追跡 |

`--case-name`と共通schemaの`--config-path`は転送する。ChatGPT版`include`の`--include-set`は維持し、Claude旧入口では維持しない。`include`はinclude setまたはinclude pathを1件以上必要とし、pathはRepoRoot相対の`/`区切りとする。

次の旧指定は成果物生成前に終了コード2で拒否する。

```text
--staged, --unstaged-only, --diff-base, --diff-target
--allow-docset-folders, --keep-bundle-dir, --diag
--max-bytes-per-part, --max-chars-per-part, --max-chars-per-file
旧basename検索
旧出力名・配置・manifest
ファイル途中切り詰め
不正文字の置換継続
```

次の旧トップレベル設定キーは読み替えず、`schemaVersion: 1`の共通設定へ移行する。

```text
outRoot, ruleFile, excludeFolders, excludeExtensions
excludeNamePatterns, secretNamePatterns, allowedToolIncludeFiles
```

旧schemaは現行CLI呼出し前に終了コード2で拒否する。委譲後の終了コードと成果物契約は各現行コマンドに従う。
