# 01 consult_bundle_claude.py 技術仕様

> File: 01_make_consult_bundle_spec.md
> Version: 2.0.0
> Updated: 2026-06-07

---

## 概要

`consult_bundle_claude.py` は、Git管理されたローカルリポジトリからClaudeへの相談用バンドルMDを生成するPythonスクリプトです。

出力は単一のMarkdownファイル（`<DocSet>_<Mode>[_<CaseName>].md`）です。
300,000文字を超える場合は `_part1.md` / `_part2.md` に分割されます。

---

## 動作要件

- Python 3.9 以上
- Git がインストールされ、`git` コマンドがPATHに通っていること
- 対象ディレクトリが `git init` 済みであること（`diff` モードはコミット履歴が必要）
- 外部ライブラリ不要（標準ライブラリのみで動作）

---

## 引数一覧

| 引数 | 必須 | 既定値 | 説明 |
|---|---|---|---|
| `--mode` | ✓ | — | 動作モード（`map` / `repo` / `include` / `diff`） |
| `--repo-root` | ✓ | — | リポジトリルートのパス |
| `--case-name` | | `""` | 生成物ファイル名に付与する識別名 |
| `--config-path` | | `""` | 設定ファイルのパス（省略時は自動探索） |
| `--include-paths` | | `[]` | includeモードで対象とするパス（スペース区切りで複数指定可） |
| `--staged` | | off | diffモードでstaged差分を対象にする |
| `--unstaged-only` | | off | diffモードでunstaged差分のみを対象にする |
| `--diff-base` | | `""` | diffモードの比較元ref（例：`HEAD~1`） |
| `--diff-target` | | `""` | diffモードの比較先ref（例：`HEAD`） |
| `--max-chars-per-part` | | `300000` | 1ファイルあたりの最大文字数 |
| `--max-chars-per-file` | | `300000` | ファイル内容の最大文字数 |
| `--allow-docset-folders` | | off | DocSet管理フォルダを除外対象から外す（デバッグ用） |
| `--diag` | | off | 診断出力を有効化（トラブルシュート用） |

---

## モード詳細

### map モード

リポジトリ全体を収集範囲とし、**本文なし**の軽量地図を生成します。

- TREE（フォルダ構造）とMANIFEST（ファイル一覧）のみを出力
- ファイル本文は含まない
- include対象の候補ファイルを洗い出すために最初に実行する

```bash
python ai-consult-tools/claude/consult_bundle_claude.py --mode map --repo-root <your-repo>
```

### include モード

`--include-paths` で指定したファイル・フォルダを**本文付き**で出力します。

- 指定方法：絶対パス / リポジトリルートからの相対パス / フォルダ名のみ / ファイル名のみ
- フォルダ名のみ・ファイル名のみ指定時：同名が複数ヒットした場合はエラー停止
- ワイルドカード（`*` / `?` / `[]`）は非対応
- 複数パスはスペース区切りで列挙する

```bash
# 相対パス指定（複数はスペース区切り）
python ai-consult-tools/claude/consult_bundle_claude.py --mode include --repo-root <your-repo> \
  --include-paths src/controllers src/models

# ファイル名のみ指定（同名複数ヒット時は停止）
python ai-consult-tools/claude/consult_bundle_claude.py --mode include --repo-root <your-repo> \
  --include-paths App.php
```

### diff モード

Git差分を出力します。修正後のレビューに使います。

差分のスコープは以下のオプションで制御します：

| オプション | 差分スコープ | DiffArgs |
|---|---|---|
| 既定（オプションなし） | HEAD vs 作業ツリー | `diff --no-color --no-ext-diff HEAD` |
| `--staged` | HEAD vs ステージング | `diff --no-color --no-ext-diff --staged HEAD` |
| `--unstaged-only` | ステージング vs 作業ツリー | `diff --no-color --no-ext-diff` |
| `--diff-base` + `--diff-target` | 指定ref間 | `diff --no-color --no-ext-diff <Base> <Target>` |

```bash
# 未コミット差分（既定）
python ai-consult-tools/claude/consult_bundle_claude.py --mode diff --repo-root <your-repo>

# staged差分
python ai-consult-tools/claude/consult_bundle_claude.py --mode diff --repo-root <your-repo> --staged

# ref間差分
python ai-consult-tools/claude/consult_bundle_claude.py --mode diff --repo-root <your-repo> \
  --diff-base HEAD~1 --diff-target HEAD
```

リネーム検出（`-M` オプション）は有効化されており、生成物のDiff Indexの `RenameDetection` 欄に記録されます。

### repo モード

リポジトリ全体を**本文付き**で出力します。

- 除外設定に従い、収集対象ファイルを全件取得して本文を出力
- 大規模リポジトリでは出力が大きくなるため、通常はmap→includeを優先する
- mapでは不足する場合の広い参照として使用する

```bash
python ai-consult-tools/claude/consult_bundle_claude.py --mode repo --repo-root <your-repo>
```

---

## 設定ファイル（consult.config.json）

スクリプトは起動時に設定ファイルを自動探索します。

**探索順：**
1. `--config-path` で明示指定されたパス
2. `<RepoRoot>/ai-consult-tools/local/claude/consult.config.json`
3. `<RepoRoot>/.consult/consult.config.json`

設定ファイルが見つからない場合はエラーで停止します。`consult.config.example.json` をコピーして作成してください。

### 設定項目一覧

| キー | 型 | 説明 |
|---|---|---|
| `outRoot` | string | 生成物の出力先（RepoRootからの相対パス） |
| `ruleFile` | string | 運用ルールファイルのパス（バンドルのINDEXに記載される） |
| `excludeFolders` | string[] | 除外するフォルダ名のリスト |
| `excludeExtensions` | string[] | 除外する拡張子のリスト（例：`.jpg`、`.zip`） |
| `excludeNamePatterns` | string[] | 除外するファイル名パターン（例：`*.min.js`） |
| `secretNamePatterns` | string[] | 除外する機密ファイルのパターン（例：`.env*`、`*.pem`） |
| `allowedToolIncludeFiles` | string[] | ツールファイル自身をinclude対象にする場合のホワイトリスト |

---

## 出力形式

出力ファイルは以下のセクションで構成されます：

| セクション | 内容 |
|---|---|
| `## 参照確定` | 唯一の正の宣言・DocSet・モード |
| `## Meta` | 生成条件（DocSet・モード・パス・コマンドライン等） |
| `## Limits` | 文字数制限 |
| `## Exclusions` | 適用された除外ルール |
| `## Stats` | 含有ファイル数・バイト数・グループ別集計 |
| `## Diff Index` | （diffモードのみ）差分ファイル一覧・DiffArgs |
| `# TREE` | 含有ファイルのフォルダツリー |
| `# MANIFEST` | ファイル一覧（CSV形式：パス・バイト数・更新日時・SHA256・グループ等） |
| `# CONTENT` | ファイル本文（includeモード・repoモード）または差分（diffモード） |

### DocSet

DocSetはバンドル生成時刻（JST）から自動生成されます。

フォーマット：`yyyyMMddHHmmss`（例：`20260605183541`）

生成物のファイル名：`<DocSet>_<Mode>[_<CaseName>].md`

---

## グループ分類

ファイルは拡張子に応じて以下のグループに分類されます：

| グループ | 拡張子 |
|---|---|
| `config` | `.conf` `.htaccess` `.ini` `.json` `.yaml` `.yml` |
| `docs` | `.md` `.txt` |
| `js` | `.cjs` `.js` `.mjs` |
| `php` | `.inc` `.php` `.phtml` |
| `sql` | `.sql` |
| `styles` | `.css` `.less` `.sass` `.scss` |
| `ts` | `.ts` `.tsx` |
| `misc` | その他 |

---

## 診断モード（--diag）

`--diag` を付けると、スクリプトの詳細なエラー情報（スタックトレース）をコンソールに出力します。

通常の相談フローでは使用しません。スクリプトが意図しないエラーで停止した場合のトラブルシュート時のみ使用してください。

```bash
python ai-consult-tools/claude/consult_bundle_claude.py --mode include --repo-root <your-repo> \
  --include-paths src --diag
```
