# SECURITY.md

> File: `shared/SECURITY.md`
> Updated: 2026-07-24
> Status: AI相談運用基盤v4

## 1. この文書の役割

本書は、構造走査、本文収集、review、生成bundleにおける機密情報とローカル情報の取扱いを定義する。

技術的な設定スキーマは`docs/01_current_spec.md`を参照する。

## 2. 自動除外だけに依存しない

現在の実装は、構造走査に組み込み除外規則を持つ。主な対象は以下である。

```text
.git
node_modules
vendor
主要build生成物
consult生成物
ai-consult-tools/local/
ai-consult-tools/archive/
.env系
秘密鍵・証明書
credential・secretを含む代表的な名前
```

ただし、自動除外は機密性を保証しない。

- ファイル本文の秘密情報を意味解析しない
- 通常名のソースや設定へ埋め込まれたAPIキーを検出できない
- プロジェクト固有の秘密名をすべて把握できない
- 明示対象やローカル文書には、共有を意図した固有情報が含まれる場合がある

bundle生成前と外部共有前に、人が対象と内容を確認する。

## 3. 共通設定で追加除外する

現行共通設定で使用できる関連項目は以下である。

| キー | 用途 |
|---|---|
| `filters.excludePaths` | 本文収集から追加除外する |
| `filters.binaryExtensions` | 追加拡張子をバイナリとして扱う |
| `filters.maxTextBytes` | 1ファイルの本文収集上限 |
| `inventory.excludePaths` | 構造走査から追加除外する |

構造にも本文にも出したくないパスは、必要に応じて両方へ指定する。

`outputs.chatgpt.outRoot`と`outputs.claude.outRoot`の実設定値は生成物専用領域である。既定値か任意値か、現在のtarget、tracked／untrackedを問わず、各outRoot自体と全子孫を列挙、読込、hash計算、構造資料、bundle、`MANIFEST.csv`、`SKIPPED.md`から無言で完全除外する。outRootはglobではなく、`[`などを文字として扱うリテラルなディレクトリ境界であり、一般の`excludePaths`とは別に判定する。兄弟の正規ソースは相対パスと本文を維持する。

outRootまたは子孫の明示include／review targetは正式成果物を作らずエラーにする。現在生成した成果物を受け取るためのCLI通知は維持するが、そのパスを後続bundleへ継承しない。ツールは出力先配下の過去bundle、ZIP、sidecar、Claude Markdown、一時ディレクトリを収録せず、削除、移動、上書きもしない。この自動除外はほかの機密情報除外を置き換えない。

```json
{
  "schemaVersion": 1,
  "filters": {
    "excludePaths": [
      "private/",
      "config/production.php"
    ],
    "binaryExtensions": [
      ".psd",
      ".clip"
    ],
    "maxTextBytes": 2000000
  },
  "inventory": {
    "excludePaths": [
      "private/",
      "config/production.php"
    ]
  }
}
```

設定内のパスはRepoRoot相対、`/`区切りの正規形で記載する。

旧版の`secretNamePatterns`、`excludeFolders`、`excludeExtensions`などは現行共通設定のキーではない。未知のキーは設定エラーになる。

## 4. localファイル

以下はGit管理しない。

```text
ai-consult-tools/local/consult.config.json
ai-consult-tools/local/project_profiles.json
ai-consult-tools/local/consult.local.md
ai-consult-tools/local/cache/
```

`consult.config.json`と`project_profiles.json`へ秘密情報を書かない。

`consult.local.md`にはローカルパス、ビルドコマンド、remote URL、deploy手順などを記載できるが、パスワード、トークン、秘密鍵、接続文字列は記載しない。

`consult.local.md`をstart bundleへ含める場合、外部共有前に内容を確認する。

## 5. 明示対象とreview

`start --include-paths`では、必要なファイルだけを指定する。

- `.env`、秘密鍵、証明書、認証情報を指定しない
- 実データや個人情報を含むexportを指定しない
- DB dump、ログ、バックアップを安易に含めない
- 不足・除外・失敗は`PATH_INDEX.md`と`SKIPPED.md`で確認する

`review`では差分と未追跡ファイルの本文が含まれる。commit対象でなくても、対象パス内の変更がbundleへ入る可能性があるため、`--target-paths`を限定する。

## 6. 生成物

ChatGPT ZIPとその`.zip.sha256` sidecar、Claude Markdownは正式成果物である。ZIPとClaude Markdownは、収録したソース、差分、manifest、ローカル情報を含む場合がある。sidecarはZIPの大文字SHA-256とbasenameだけを記録し、絶対パスやほかのファイルを列挙しない。

- `consult_case/`をGit管理しない
- 公開リポジトリや共有ストレージへ無条件に置かない
- 外部共有前に`INDEX.md`、`PATH_INDEX.md`または`DIFF_INDEX.md`、`SKIPPED.md`、`MANIFEST.csv`を確認する
- ChatGPT成果物はZIPとsidecarを同じディレクトリの一組として扱い、`<64桁の大文字SHA-256> *<ZIP basename><CRLF>`の形式とZIP hashの一致を確認する
- 不要な生成物は、必要なレビューと記録が終わった後に削除できる
- bundleを恒久的な仕様正本として保管しない

## 7. 問題の報告

このツールの境界判定、除外、収集、出力にセキュリティ上の問題を確認した場合は、公開前にリポジトリ管理者へ報告する。秘密情報そのものを公開Issueへ貼り付けない。
