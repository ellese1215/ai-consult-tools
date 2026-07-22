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

### 相談開始

```text
python ai-consult-tools/consult.py start --target <chatgpt|claude> --profile <name> --case-name <case> --include-set common_rules --include-paths <path>...
```

### レビュー

```text
python ai-consult-tools/consult.py review --target <chatgpt|claude> --profile <name> --case-name <case> --target-paths <path>...
```

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
