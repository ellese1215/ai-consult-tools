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

秘密情報、認証情報、個人情報は記載しません。

## 2. プロジェクト別コマンド

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

## 3. 共通CLI

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

## 4. Git・remote・公開手順

```text
private remote:
  name: <name>
  target: <scope>

public remote:
  name: <name or none>
  url: <url or none>
  target: <scope or none>

push procedure:
  <commands>

failure rule:
  <stop condition>
```

強制push、subtree、deployなどの個別手順は、確認済みの内容だけを記載します。

## 5. プロジェクト固有の注意事項

自動生成ファイル、直接編集禁止ファイル、deploy前確認など、現在有効な注意事項だけを記載します。

一時的な作業状況や別案件の未コミット変更は、恒久的なlocal文書へ残しません。
