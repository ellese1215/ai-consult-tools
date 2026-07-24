# AI相談 詳細手順

> File: `shared/01_ai_consult_procedures.md`
> Updated: 2026-07-24
> Workflow schema: `ai-consult-workflow/v1`

## 1. この文書の役割

本書は、最上位契約を実行するための受渡し、bundle確認、修正ラリー、Git前後確認、thread／task立て直しの手順を定義する。

- 役割と必須ゲートは`shared/00_ai_consult_operation_rules.md`
- 共通工程状態の書式は`shared/02_consult_template.md`
- CLIの正確な入出力契約は`docs/01_current_spec.md`
- ローカル環境と主要コマンドは`local/consult.local.md`
- 機密情報の取扱いは`shared/SECURITY.md`

## 2. 開始時に有効な工程状態を復元する

次の証跡を同じreview targetへ結び付けて読む。

1. Codexが作成した最新の`handoff/current.md`
2. そのtargetを特定したCodex最終報告とreview bundle
3. 対応する最新のWorkレビュー結果
4. Userが提示したstage／commit／push結果
5. 実リポジトリのbranch、HEAD、status、remote照合結果

実リポジトリの事実を最優先する。Work承認は対象bundleを特定した最新結果、commit／pushはUserのコマンド結果とリポジトリ照合を優先する。
チェックポイントからBase、変更範囲、Codex証跡、次ゲートを確認し、外部証跡から後続結果を確認する。
必要な証跡を同じtargetへ結び付けられない場合、または証跡間に矛盾がある場合は次工程へ進まない。

## 3. start bundle

### 3.1 用途

start bundleは、実リポジトリを直接読めないWorkまたはCodexへ、仕様確定や変更開始に必要な生成時点の参照資料を渡す。
同じリポジトリを直接読める相手には通常生成しない。

### 3.2 include setの選択

通常のプロジェクト引き継ぎは次を収録する。

```text
--include-set common_rules
+ 案件ごとのhandoff/current.md
+ 次の一作業に必要な仕様、実装、試験
```

`common_rules`は次の3件だけである。

```text
ai-consult-tools/shared/00_ai_consult_operation_rules.md
ai-consult-tools/shared/02_consult_template.md
ai-consult-tools/local/consult.local.md
```

AI相談ツール自体の保守は次を収録する。

```text
--include-set common_rules
--include-set ai_consult_maintenance
+ ai-consult-tools/docs/handoff/current.md
+ 作業対象
```

`ai_consult_maintenance`はREADME、現行技術仕様、本手順、SECURITY、local文書例を収録する。
詳細な技術資料を通常のプロジェクト引き継ぎへ常時含めない。

### 3.3 生成

Windows／PowerShellの書式例：

```powershell
cd C:\xampp\htdocs

python .\ai-consult-tools\consult.py start `
  --target chatgpt `
  --profile <profile> `
  --case-name <case> `
  --include-set common_rules `
  --include-paths `
    "<project-handoff-current>" `
    "<next-task-required-path>"
```

実行時はプレースホルダーを実在値へ置換し、不要な行を削る。
AI相談ツール保守では`--include-set ai_consult_maintenance`を追加する。
引数、構造snapshot、出力、sidecarの厳密な契約は現行技術仕様に従う。

### 3.4 確認順

1. CLI終了コードと成功出力
2. `INDEX.md`
3. `STRUCTURE_STATUS.md`
4. `PATH_INDEX.md`
5. `SKIPPED.md`
6. `MANIFEST.csv`
7. 収録本文

不足またはskipが次工程の判断を変える場合は、そのbundleを使用しない。

## 4. WorkからCodexへの受渡し

Workはread-only調査を完了し、目的、Base HEAD、対象、保護対象、受入条件、必要な文書と試験、許可操作を外部の限定指示としてCodexへ渡す。
Workはこの受渡しのためにGit管理ファイルを編集しない。
複数の独立変更を一つの曖昧な作業へまとめない。

## 5. Codexの変更と証跡

1. RepoRoot、branch、HEAD、worktreeを実確認する。
2. 対象ファイルの基準hashまたはBase HEADとの差分を確認する。
3. 対象外差分を記録し、編集対象から分離する。
4. 許可された対象だけを変更する。
5. 仕様、文書、設定、試験を同じ作業単位で同期する。
6. 対象試験、全体試験、差分検査を実行する。
7. `base_commit`を開始時HEADへ固定し、実際の変更パスと試験結果を`codex_evidence`へ記録する。
8. Workへ渡す時点のGit内チェックポイントを作成する。
9. チェックポイントを含む実際の変更パスだけでreview bundleを一度生成する。

Work承認、commit、pushではこの`base_commit`を上書きしない。
新たな実質的変更サイクルだけが、開始前HEADから新しいチェックポイントを作る。

新規、削除、renameがある場合は、第10章に従って構造同期の可否を先に判定する。

## 6. review bundle

### 6.1 用途

review bundleは、Base HEADに対する生成時点のstaged、unstaged、未追跡をWorkが独立レビューするための資料である。
変更実装の参照資料としてstart bundleを作り直さない。

### 6.2 生成

```powershell
cd C:\xampp\htdocs

python .\ai-consult-tools\consult.py review `
  --target chatgpt `
  --profile <profile> `
  --case-name <review-case> `
  --target-paths `
    "<changed-path-1>" `
    "<changed-path-2>"
```

`--target-paths`には実際に変更したRepoRoot相対パスをすべて列挙する。
Git管理外かつignore対象のファイルは、ディレクトリではなく完全なファイルパスを指定する。
生成後に対象を変更した場合は、そのbundleを最終成果物として扱わず、新しいcase名で再生成する。

### 6.3 確認順

1. CLI終了コード、`bundle_path:`、`bundle_sha256:`、`sidecar_path:`、`sidecar_match: true`
2. `INDEX.md`
3. `DIFF_INDEX.md`
4. `SKIPPED.md`
5. `MANIFEST.csv`
6. 各差分本文

各targetが差分項目または`SKIPPED.md`の理由へ対応していることを確認する。

## 7. Work独立レビューと修正ラリー

WorkはBase HEAD、Target、受入条件、review bundleを確認し、次を判定する。

1. 対象と収録範囲が一致する
2. 確定仕様と受入条件を満たす
3. 変更漏れと不要変更がない
4. 対象外差分が保護されている
5. 文書と設定と試験が一致する
6. 試験証跡が再現可能である

Workは`status`と`evidence`を持つ構造で外部レビュー結果を返し、`evidence`で対象bundleを一意に特定する。
Work承認はGitファイルへの追記がなくても有効である。

工程遷移を次へ統一する。

| From | Condition / evidence | To |
|---|---|---|
| Codex handoff | checkpoint and review bundle ready | Work review |
| Work changes requested | numbered findings tied to target | Codex correction |
| Work approved | approval tied to target | User commit decision |
| Commit completed | result_commit and repository verification | User push decision |
| Push verified | remote_commit matches required remote | completed |

`changes_requested`の場合だけ、Codexは番号付き事項を修正し、影響する試験を再実行する。
修正後は新しいチェックポイントとreview bundleを作成し、Workが最新targetを再レビューする。
`approved`の場合は状態同期を挟まずUserへ進み、チェックポイント更新だけを目的としてCodexへ戻さない。

## 8. commit前後

Work承認後も、Userがstage／commitを判断するまでworktreeを変更工程の成果物として保持する。

commit前：

1. Work承認が最新差分を対象としていることを確認する。
2. 変更予定パスと保護対象を表示する。
3. Userがstage／commitを明示判断する。
4. 指定パスだけをstageする。
5. staged差分と対象パスを照合する。
6. Userが承認した内容だけをcommitする。

commit後：

1. commit IDを`result_commit`として外部報告へ記録する。
2. commit ID、変更パス、worktreeを実リポジトリと照合する。
3. `base_commit`は変更せず、push判断を別ゲートとしてUserへ提示する。

commit結果の同期だけを目的として`handoff/current.md`を更新しない。

## 9. push前後

push前にremote、branch、公開範囲、認証、派生操作を確認し、Userが対象ごとに判断する。
origin push、public subtree push、release、deployを一つの承認にまとめない。

push後はlocal HEADと対象remote先端を照合し、対象remoteの結果を`remote_commit`として外部報告へ記録する。
`base_commit`は変更せず、push結果の同期だけを目的として`handoff/current.md`を更新しない。
失敗時は原因と現在状態を記録し、force pushや別の公開方法へ自動移行しない。
環境固有の公開手順は`local/consult.local.md`が参照するオンデマンドrunbookに従う。

## 10. チェックポイント、TODO、履歴、構造

`handoff/current.md`は、Codexがreview targetをWorkへ渡す時点のGit内チェックポイントである。
Work承認、commit、pushのたびには更新せず、工程移行の追記や完了実況を蓄積しない。
外部結果は対象bundle、User報告、実リポジトリ照合へ結び付けて保持する。
新たな実質的変更が必要な場合だけ、Codexが新しい変更サイクルの通常targetとしてチェックポイントを更新する。

TODOは未完了作業の管理に使い、チェックポイントや外部証跡を複製しない。
履歴は将来の判断、監査、再現に必要な決定だけを記録する。

構造が変わる場合は、永続`folder_tree.txt`の開始時状態を確認する。

- cleanで、今回の新規・削除・renameだけを反映できる場合：`structure sync`を実行し、更新パスをレビュー対象へ含める。
- 既存差分がある場合：`structure sync`を実行せず、`folder_tree.txt`を編集せず、保留理由を証跡へ記録する。

`start`はlive inventory snapshotをbundle内へ生成するため、永続構造同期の代替でも実行契機でもない。

## 11. thread／taskの立て直し

Phase完了、変更単位完了、レビュー完了、次の一作業確定を立て直しの候補点とする。

1. 最新チェックポイント、Codex target証跡、Work結果、User結果、実リポジトリを確認する。
2. 同じreview targetへ結び付く有効な状態と次の一作業だけを短い引き継ぎ文へ記載する。
3. 次の担当が実リポジトリを読めるか確認する。
4. 必要な場合だけ最新bundle一つを使用する。
5. 状態同期だけのチェックポイント変更を作らない。
6. 共通ルール全文、完了ログ、過去bundle一覧を転記しない。

作業途中で安全に完了できる現在の一作業を放棄して、立て直しだけを先行しない。
