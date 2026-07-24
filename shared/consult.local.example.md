# consult.local.md

> File: `local/consult.local.md`
> このファイルはGit管理外です。
> `shared/consult.local.example.md`をコピーし、実環境に合わせて編集します。

## 1. 環境

| 項目 | 値 |
|---|---|
| RepoRoot | `<absolute-repo-root>` |
| OS | `<Windows / macOS / Linux>` |
| Shell | `<PowerShell / bash / zsh>` |
| Shell version | `<version>` |

秘密情報、認証情報、個人情報は記載しません。

## 2. ユーザー向けコマンド提示設定

環境固有値を実環境に合わせて記入する。特定のShell、version、文字コードを全環境共通の固定値にしない。

| 項目 | 値 |
|---|---|
| エラー処理 | `<stop-on-error setting or equivalent>` |
| StrictModeまたは相当する安全設定 | `<setting>` |
| 一括コピーの単位 | `<one executable unit per code block>` |
| RepoRoot、前提、対象パスの明示方法 | `<method>` |
| 実行後に確認する出力 | `<outputs and success criteria>` |
| 外部スクリプトの文字コード | `<encoding safe for the selected environment>` |
| 外部スクリプトの構文確認方法 | `<parser or validation command>` |
| stage、commit、pushの分割と確認境界 | `<separate units and explicit approvals>` |
| push後のlocal／remote照合 | `<comparison method>` |
| subtree、公開remote、deployの停止条件 | `<stop conditions>` |
| bundle生成の標準形 | `<direct consult.py start command>` |
| folder_tree.txtの位置づけ | `<persistent navigation aid; only structure sync updates it; start includes a live-snapshot-generated item without changing it>` |
| start前の構造確認 | `<not a required gate>` |
| ChatGPT成果物の確認 | `<read bundle_path, bundle_sha256, sidecar_path, and sidecar_match from CLI output; do not guess names>` |
| `.Count`参照対象の配列化 | `<wrap the whole producing expression or pipeline in an array construct>` |
| native command終了コード確認 | `<check immediately after every native command before using its output>` |
| 単一行出力の確認 | `<arrayize, require exactly one non-empty line, then read index 0>` |
| プレースホルダーの扱い | `<never present placeholders as directly executable commands>` |

コマンド全文は実行前提と確認方法を含む一括コピー可能な単位で提示し、状態を変える工程は直前の結果と必要な確認を経てから進める。

## 3. プロジェクト別コマンド

変更内容に応じて必要となるビルド、試験、静的解析、DB確認などを記載します。

```text
<profile-name>:
  build: <command or none>
  test: <command or none>
  manual_check: <procedure or none>
```

例：

```powershell
cd <absolute-repo-root>
npm run build --workspace=<workspace>
```

## 4. 共通CLI

### 構造

```text
python ai-consult-tools/consult.py structure sync
python ai-consult-tools/consult.py structure check
python ai-consult-tools/consult.py find <query> --profile <name>
```

`structure sync`と`structure check`は、bundleを生成せず構造資料を保守・診断する場合に使用する。`structure check`のstale結果を`start`の停止条件にしない。

### 相談開始

```text
python ai-consult-tools/consult.py start --target <chatgpt|claude> --profile <name> --case-name <case> --include-set common_rules --include-paths <path>...
```

`common_rules`は、README、現行仕様、共通運用ルール、最小テンプレート、このローカル運用情報を収録する引き継ぎ用最小運用セットとして維持する。各ファイルを`--include-paths`へ重ねて指定しない。

`start`は上記CLIを直接実行する。独自wrapperで事前の`structure check`や一時設定生成を追加しない。永続`folder_tree.txt`と構造インデックスを更新するのは`structure sync`だけであり、`start`は両方を変更せず、live inventory snapshotから構造情報をbundle内生成する。`stale`、`missing`、`invalid`は`STRUCTURE_STATUS.md`へ報告されるが停止条件ではない。設定済みChatGPT／Claude `outRoot`はglobではないリテラルな生成物専用ディレクトリ境界であり、自身と全子孫をtarget、tracked／untrackedを問わず収集から無言で完全除外する。自動除外は`SKIPPED.md`へ記録せず、明示include／review targetは成果物生成前にエラーになる。兄弟の正規ソースの相対パスと本文、現在成果物のCLI通知は維持し、既存成果物を削除、移動、上書きしない。

ChatGPTの正式成果物はZIPと`.zip.sha256`の2点である。sidecarはUTF-8 BOMなしの`<64桁の大文字SHA-256> *<ZIP basename><CRLF>`という1行で、同じディレクトリのZIPと照合する。通常wrapperはCLIの`bundle_path:`、`bundle_sha256:`、`sidecar_path:`、`sidecar_match: true`を利用し、成果物名を推測しない。Claudeにはsidecarを要求しない。

### レビュー

```text
python ai-consult-tools/consult.py review --target <chatgpt|claude> --profile <name> --case-name <case> --target-paths <path>...
```

ignore対象のローカルファイルをreviewする場合は、必要なファイルの完全相対パスだけを明示する。ignore対象ディレクトリ配下を自動収集させない。各明示対象が収録項目または`SKIPPED.md`のどちらへ出たかを確認する。

相談ごとの長いファイル一覧や完了済みPhaseのコマンドは、この文書へ蓄積しません。

## 5. Git・remote・公開手順

```text
private remote:
  name: <name>
  target: <scope>

public remote:
  name: <name or none>
  url: <url or none>
  target: <scope or none>

push procedure:
  <separate commit / private push / public push or deploy units>

confirmation boundary:
  <explicit approval required before commit and separate approval required before each push>

post-push verification:
  <local HEAD and target remote comparison method>

failure rule:
  <subtree / public remote / deploy stop condition>
```

強制push、subtree、deployなどの個別手順は、確認済みの内容だけを記載します。

## 6. プロジェクト固有の注意事項

自動生成ファイル、直接編集禁止ファイル、deploy前確認など、現在有効な注意事項だけを記載します。

一時的な作業状況や別案件の未コミット変更は、恒久的なlocal文書へ残しません。
