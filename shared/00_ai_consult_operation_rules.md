# AI相談共通運用ルール

> File: `shared/00_ai_consult_operation_rules.md`
> Updated: 2026-07-21
> Rules revision: 20260721-simplified-r1
> Scope: Chat / Work / Codexによる仕様検討、実装、レビュー、引き継ぎ

## 1. 正本

正本はローカルの現行Gitリポジトリである。ZIPは、リポジトリを直接読めない相談先へ生成時点の状態を運ぶための資料であり、恒久的な正本ではない。

| 判断対象 | 主な根拠 |
|---|---|
| 共通運用 | 本書 |
| CLI・bundle・出力の技術仕様 | `docs/01_current_spec.md`と現行コード |
| ローカル環境・コマンド | `local/consult.local.md` |
| プロジェクト内の読む順序 | `docs/<project>/README.md` |
| 現在のPhase・未完了事項 | `00_project_status.md`、`todo/current.md` |
| 次の一作業 | `handoff/current.md`または今回の指示文 |
| 仕様・実装事実 | 要件書、設計書、現行コード、試験、必要に応じて実DB |

会話だけを最終仕様にしない。会話で確定した内容は、実装と同じ作業単位で正本文書へ反映する。

同種の新しいbundleが提示されたら古いものは使用しない。添付されているだけの資料を、用途確認なしに今回の正本とみなさない。

## 2. 作業開始前の確認

具体的な提案、編集、コマンド提示、レビュー結論の前に、次を確定する。

1. 今回の目的と完了条件
2. 実際に読めるリポジトリ、branch、commitまたは有効なbundle
3. 対象ファイルと対象外・保護対象
4. 確定仕様と未確定事項
5. 調査、編集、試験、公開など許された作業範囲

Chat、Work、Codexという名称だけからファイル可視範囲を推測しない。現在地、対象パス、Git、HEAD、worktreeを実確認する。

次の事項が結果を変える場合だけ作業を止めて質問する。

- 正本またはbase / targetが確定できない
- 必須の仕様、コード、実DBを読めない
- 既存の未コミット変更と安全に分離できない
- 破壊的変更、削除、公開、外部送信に新しい承認が必要

結果を変えない不足については、対象外または未確認と明記して進める。

## 3. 標準フロー

```text
Chatで自由検討（任意）
→ Workで仕様確定
→ Codexで実装・文書同期・試験
→ Workで最新差分をレビュー
→ commit / push
→ 次の相談に必要な場合だけstart bundleを一度生成
```

| 工程 | 渡すもの |
|---|---|
| Chat | 通常は添付不要 |
| リポジトリを読めないWorkで仕様確定 | 短い依頼文、最新start bundle一つ |
| リポジトリを読めるCodexで実装 | 確定した実装指示。bundleは不要 |
| リポジトリを読めないCodexで実装 | 確定した実装指示、最新start bundle一つ |
| Workで実装レビュー | レビュー依頼文、最新review bundle一つ |
| 同じCodexでレビュー指摘を修正 | 番号付き修正事項だけ |

旧ツール配布ZIP、過去bundle、通常ログ、重複資料は次の工程へ渡さない。解決済みまたは本件と無関係な失敗ログも渡さない。ただし、未解決の障害自体を次工程で診断する場合は、再現条件、実行コマンド、判断に必要な最小限のエラー出力だけを渡す。複数ZIPを入れ子にしたhandoff compositeは、明示的な必要がある場合だけ作る。

## 4. bundle

ツール配布ZIP、start bundle、review bundleを区別する。

- start bundle：仕様検討・実装開始用の現行資料
- review bundle：基準HEADに対する生成時点のworktree状態（staged、unstaged、未追跡）
- ツール配布ZIP：相談ツール自体を保守する場合だけ使用

### 4.1 start bundleへ収録するもの

`--include-set common_rules`で共通運用ルールとローカル運用情報を収録する。`--include-paths`には、次のうち実在して今回必要なものだけを指定する。

- `docs/<project>/README.md`
- `docs/<project>/00_project_status.md`
- `docs/<project>/todo/current.md`
- `docs/<project>/handoff/current.md`
- 次の一作業に必要な要件書・設計書
- 判断に必要な場合だけ対象コードと対象テスト

存在しない任意文書は作成しない。プロジェクト全体、過去bundle、旧ツール、ログ、別案件は収録しない。

`start`が自動生成する次のファイルは手動指定しない。

```text
INDEX.md
REPO_OVERVIEW.md
PROJECT_TREE.md
STRUCTURE_STATUS.md
PATH_INDEX.md
SKIPPED.md
MANIFEST.csv
```

### 4.2 start bundle生成コマンド

Windows / PowerShellの標準形：

```powershell
cd C:\xampp\htdocs

python .\ai-consult-tools\consult.py start `
  --target chatgpt `
  --profile <profile> `
  --case-name <case> `
  --include-set common_rules `
  --include-paths `
    "docs/<project>/README.md" `
    "docs/<project>/00_project_status.md" `
    "docs/<project>/todo/current.md" `
    "docs/<project>/handoff/current.md" `
    "<next-task-required-path>"
```

実際の引き継ぎでは、プレースホルダーを実在値へ置換し、存在しないパスと不要な行を削除した、実行可能なコマンド全文を提示する。

ChatGPT向けZIPの標準出力先：

```text
C:\xampp\htdocs\ai-consult-tools\chatgpt\consult_case\<BundleLabel>\<BundleLabel>.zip
```

添付しやすさを理由に出力先を`Downloads`などへ変更しない。通常はこのZIP一つだけを添付する。別の検証済み手順でSHA-256 sidecarを生成した場合だけ併記できる。

### 4.3 review bundle生成コマンド

```powershell
cd C:\xampp\htdocs

python .\ai-consult-tools\consult.py review `
  --target chatgpt `
  --profile <profile> `
  --case-name <case> `
  --target-paths `
    "<changed-path-1>" `
    "<changed-path-2>"
```

Git変更として確認できる対象パスだけを指定する。削除済みファイルは削除前のRepoRoot相対パスを指定する。review時にstart bundleを作り直さない。

## 5. 引き継ぎ文

引き継ぎ文には次だけを記載する。

```text
対象プロジェクトと現在のPhase
基準branch / commit
完了した範囲
次に行う一作業
対象文書・対象実装
対象外・保護対象
未解決事項
今回添付する唯一の成果物名
bundleが必要な場合は、実在値へ置換済みの生成コマンド全文
```

共通ルール全文、過去bundle一覧、完了済み作業の詳細ログは転記しない。

## 6. 実装・レビュー・Git

- Codexは編集前に対象ファイル、HEAD、worktree、プロジェクト正本を確認する。
- 確定仕様、実装、正本文書、試験を同じ作業単位でそろえる。
- ユーザーの既存変更と対象外ファイルを変更、削除、stageしない。
- レビューは正確な基準HEADに対するreview bundle生成時点のworktree状態を対象にし、仕様適合、変更漏れ、副作用、試験を確認する。
- Workでreview bundleをレビューする場合は、本文より先に`DIFF_INDEX.md`、`SKIPPED.md`、`MANIFEST.csv`を確認する。skipまたは収録不足が結論に影響する場合は承認しない。
- 新規、削除、renameでリポジトリ構造が変わる場合は、review bundle生成前に`folder_tree.txt`とローカル構造インデックスの同期可否を確認する。`folder_tree.txt`に今回対象外の既存差分がある場合は上書きせず、同期を保留した理由を完了報告または引き継ぎに明記する。
- 認証、権限、DB、削除、公開範囲、大規模構造変更はWorkの独立レビューを必須とする。
- 軽微な文言、CSS、限定文書修正は、Codexのdiff確認と必要な試験で完了できる。
- reviewと試験の完了後、対象を限定してcommit / pushする。`git add .`とRepoRoot全体への`git add -A`は使わない。
- push後はローカルHEADと対象remoteの先端を確認する。

## 7. 誤認時の復旧と禁止事項

誤認が判明したら、誤った前提から導いた未確定結論を無効化し、第2章の確認からやり直す。自分の過去回答を現行ファイルより上位に置かない。

次を禁止する。

- 実在確認していないファイル、コマンド、profile、パスの提示
- 現行設定を確認しないbundle出力先の変更
- 旧ツールや過去bundleを通常相談の根拠にすること
- 同種の新旧bundleを同時に有効とすること
- 仕様未確定のまま結果を左右する判断を補完すること
- 運用資料の作成自体を本来の相談・実装・レビューより大きくすること

## 8. 完了条件

- 目的と現在の正本を一文で説明できる
- 合意した変更だけが反映されている
- 仕様、実装、文書、試験が矛盾していない
- 対象外の変更を巻き込んでいない
- 次へ渡す資料が最小構成である
- 次の担当が過去会話を読み直さず一作業を開始できる
