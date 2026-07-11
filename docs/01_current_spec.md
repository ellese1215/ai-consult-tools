# AI相談運用基盤 v4 現行技術仕様

> File: `docs/01_current_spec.md`
> Updated: 2026-07-11

## 1. この文書の役割

本書は、AI相談運用基盤v4の共通CLI、設定、構造管理、bundle、物理出力の現行技術仕様を定義する。

文書の役割は以下のように分離する。

| 文書 | 役割 |
|---|---|
| `README.md` | 公開入口、導入、基本的な利用方法 |
| `shared/00_ai_consult_operation_rules.md` | 相談、合意、変更、確認の運用ルール |
| 本書 | 現行技術仕様 |
| `docs/00_v4_design_outline.md` | V4移行計画、設計背景、フェーズ履歴 |
| `shared/SECURITY.md` | 除外、機密情報、生成物の取扱い |
| `local/consult.local.md` | 個別環境のローカル情報 |

実装と自動試験は現行動作の検証根拠とする。実装、本書、合意済み要求に不一致が見つかった場合は、推測でどれかへ合わせず、不一致を確認してから修正する。

旧スクリプトのファイルパスは第11章の互換入口として現行契約に含む。旧モデル別文書、旧設定例、旧設定schemaは現行仕様に含めない。

---

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

### 2.3 RepoRoot

`--repo-root`を省略した場合、`ai-consult-tools`の親ディレクトリをRepoRootとする。

`--repo-root`で別のRepoRootを指定できる。設定、プロファイル、対象パス、出力先はすべてRepoRoot境界内で解決する。

---

## 3. CLI

現行CLIは以下の5系統である。

```text
find
structure sync
structure check
start
review
```

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

- ローカル構造インデックスを読み取り専用で検索する
- 検索前に現在構造とインデックスを比較する
- インデックスが未生成、古い、形式不正の場合は更新せず終了する
- 更新が必要な場合は`structure sync`を案内する
- 大文字小文字を区別しない
- `\`を`/`へ正規化し、先頭`./`と末尾`/`を除去する
- 完全相対パス、完全ファイル名、ファイル名部分一致、部分パス一致の順で優先する
- 同順位は決定的なパス順で表示する
- 複数候補を勝手に1件へ絞らない

終了コードは、一致ありが0、一致なしが1、処理エラーが2である。

### 3.3 `structure sync`

```text
python ai-consult-tools/consult.py structure sync
```

- 現在構造を1回走査する
- 同一snapshotから`folder_tree.txt`とローカル構造インデックスを生成する
- 内容が変わったファイルだけを更新する
- 追加、削除、移動候補を表示する
- 両方最新の場合は`current`、どちらかを更新した場合は`updated`を表示する

生成先は以下である。

```text
folder_tree.txt
ai-consult-tools/local/cache/repo_structure_index.json
```

### 3.4 `structure check`

```text
python ai-consult-tools/consult.py structure check
```

- 現在構造と`folder_tree.txt`、ローカル構造インデックスを比較する
- ファイルとディレクトリを変更しない
- 両方最新なら終了コード0
- 未生成、古い、形式不正なら終了コード1
- 走査・読込エラーなら終了コード2

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
- `--include-set`は複数回指定できる
- `--include-paths`はRepoRoot相対の明示対象を指定する
- bundle収集前に現在構造を1回走査する
- 同一snapshotから`folder_tree.txt`とローカル構造インデックスを必要に応じて同期する
- 同期前の状態、構造差分、同期結果を`STRUCTURE_STATUS.md`へ記録する
- 対象プロジェクトの同期後の最新構造情報を生成文書へ収録する
- 明示対象の解決結果、除外、不足、失敗を`PATH_INDEX.md`と`SKIPPED.md`へ記録する

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
- renameは現在パスと`previous_path`を保持する
- 変更もskipもない場合は成果物を作らず`review: no changes`で終了する
- 収録項目がなくてもskipが存在する場合は成果物を生成する

---

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
      "ai-consult-tools/local/consult.local.md"
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

設定内のパスはRepoRoot相対、`/`区切り、`.`と`..`を含まない正規形とする。

---

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

---

## 6. 構造管理

### 6.1 `folder_tree.txt`

- UTF-8 BOMなし
- LF
- RepoRoot相対
- `/`区切り
- フォルダとファイルのパスだけを収録
- 決定的ソート
- 構造が変わった場合だけ更新
- 手動編集禁止

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

構造走査では画像、音声、フォント、ZIPなどもパスとして記録できる。本文収集は判定済みテキストだけを対象とする。

symlinkとjunctionはパスを記録できるが、リンク先へ再帰しない。

---

## 7. 共通bundle契約

### 7.1 成果物名

DocSetは生成時刻のJSTを`YYYYMMDDhhmmss`で表した14桁である。

```text
<DocSet>_start[_<CaseName>]
<DocSet>_review[_<CaseName>]
```

`case-name`は前後空白を除去し、空白列を`_`へ変換した後、ASCII英数字、`.`、`_`、`-`以外を除去する。結果が空ならエラーとする。

### 7.2 共通生成テキスト

- UTF-8 BOMなし
- LF
- 末尾LFあり

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
- 同名の最終成果物が存在する場合は上書きせずエラーとする
- 出力先はRepoRoot内でなければならない

---

## 8. ChatGPT出力

### 8.1 配置

既定出力先は以下である。

```text
ai-consult-tools/chatgpt/consult_case/<BundleLabel>/<BundleLabel>.zip
```

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

---

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

---

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

---

## 11. 旧版互換入口

### 11.1 入口と固定target

旧ファイルパスは移行用の薄い互換ラッパーとして維持する。収集、Git差分、bundle生成は実装せず、現行共通CLIへ引数を変換して委譲する。

```text
ai-consult-tools/chatgpt/consult_bundle_chatgpt.py
ai-consult-tools/claude/consult_bundle_claude.py
```

ChatGPT版は`--target chatgpt`、Claude版は`--target claude`へ固定する。利用者による`--target`指定は受理しない。両入口とも`--repo-root`と`--profile`を必須とする。

実行時は標準エラーへ次を表示する。

```text
WARNING: legacy entry point; use ai-consult-tools/consult.py for new commands.
```

### 11.2 モード変換

| 旧モード | 変換先 | 収集範囲 |
|---|---|---|
| `map` | `start` | 明示ファイルを加えず、現行の構造生成文書だけ |
| `repo` | `start` | 選択profileの`scopeRoots` |
| `include` | `start` | `--include-set`と`--include-paths`の明示対象 |
| `diff` | `review` | 現行契約のstaged、unstaged、未追跡 |

`--case-name`とV4共通schemaの`--config-path`は現行CLIへ転送する。ChatGPT版`include`の`--include-set`は維持する。Claude旧入口では`--include-set`を維持しない。

`include`は少なくとも1件の`--include-set`または`--include-paths`を必要とする。include指定を他モードへ付けた場合は拒否する。include pathはRepoRoot相対かつ`/`区切りとし、絶対パスを受理しない。

### 11.3 維持しない旧契約

以下は互換入口で維持しない。指定された場合は成果物生成前に終了コード2で拒否し、現行入口への移行案内を標準エラーへ表示する。

```text
--staged
--unstaged-only
--diff-base
--diff-target
--allow-docset-folders
--keep-bundle-dir
--diag
--max-bytes-per-part
--max-chars-per-part
--max-chars-per-file
旧basename検索
旧出力名・配置・manifest
ファイル途中切り詰め
不正文字の置換継続
```

以下の旧トップレベル設定キーを持つ旧schemaも読み替えない。`schemaVersion: 1`の共通設定へ移行する。

```text
outRoot
ruleFile
excludeFolders
excludeExtensions
excludeNamePatterns
secretNamePatterns
allowedToolIncludeFiles
```

旧schemaを`--config-path`で指定した場合は、現行CLIを呼び出す前に終了コード2で拒否する。互換入口から委譲した後の終了コードと成果物契約は、各現行コマンドの契約に従う。
