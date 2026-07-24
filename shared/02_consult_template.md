# AI相談 工程テンプレート

> File: `shared/02_consult_template.md`
> Updated: 2026-07-24
> Workflow schema: `ai-consult-workflow/v1`

必要な形式を一つだけ選び、不要な任意項目は削る。
A～Dは同じチェックポイントschemaを参照し、工程状態を本文へ重複記述しない。

## Codex作成チェックポイント

`handoff/current.md`は、Codexがreview targetをWorkへ渡す時点で次の形にする。

```yaml
workflow_schema: ai-consult-workflow/v1
case: <stable-case-name>
base_branch: <branch>
base_commit: <review targetを作成した基準HEAD>
source_docset: <DocSet or none>
current_phase: <review phase>
current_gate: <Work review gate>
current_actor: Work
next_actor: <User if approved; Codex if changes_requested>
allowed_operations:
  - <read-only review operation>
pending_gates:
  - <gate>
codex_evidence:
  base_commit: <same base_commit>
  changed_paths:
    - <RepoRoot-relative path>
  tests:
    - <command and result>
  diff_check: <result>
work_review:
  status: pending
  evidence: null
user_decisions:
  policy:
    - <現在も有効なUser方針>
  commit:
    status: pending
    result_commit: null
    evidence: null
  push:
    status: pending
    remote_commit: null
    evidence: null
next_single_action: <Workが行う一作業>
```

`work_review`は常に`status`と`evidence`を持つ構造とする。
`user_decisions`は`policy`、`commit`、`push`を持ち、commit結果を`result_commit`、remote照合結果を`remote_commit`へ分離する。
チェックポイント作成時は通常、WorkとUserの結果が未発生なので`pending`と`null`を記録する。

`base_commit`はreview target内で不変であり、Work承認、commit、pushの結果で上書きしない。
Work結果とUser結果は対象bundleを特定した外部証跡で保持し、結果同期だけのGit変更を行わない。

## A. Workで仕様を確定する

```markdown
# <project> <topic>

- Checkpoint: <既存チェックポイントまたはnone>
- Repository facts: <branch / HEAD / status>
- Purpose: <今回確定する一つの結果>
- Decisions needed: <確定事項>
- Invariants: <変えてはいけないこと>
- Out of scope: <対象外>

Workへの依頼：
read-onlyで根拠を確認し、実装仕様、対象、対象外、受入条件、
必要な文書更新と試験、Codexへ許可する操作を確定してください。
確定結果をCodexへの限定指示として返し、Git管理ファイルは編集しないでください。
```

リポジトリを読めないWorkに限り、最新start bundle一つを添付する。

## B. Codexへ変更を依頼する

```markdown
# <project> <implementation unit>

- Prior checkpoint: <path or none>
- Repo root: <absolute path>
- Expected branch / Base HEAD: <value>
- Confirmed requirements: <確定仕様>
- Target: <変更可能なパス>
- Protected / out of scope: <既存差分と対象外>
- Acceptance criteria: <正常・異常・境界条件>
- Required docs and tests: <対象>

Codexへの依頼：
実リポジトリ、branch、HEAD、worktreeを確認してください。
許可範囲だけを変更し、文書同期、試験、差分検査を行ってください。
Base HEAD、変更パス、試験結果をcodex_evidenceへ記録し、
チェックポイントとreview bundleを同じreview targetとしてWorkへ渡してください。
```

Codexが実リポジトリを読める場合はbundleを添付しない。
読めない場合だけ最新start bundle一つを添付する。

## C. Workへ独立レビューを依頼する

```markdown
# <project> implementation review

- Checkpoint: `<handoff/current.md>`
- Base HEAD: <checkpointのbase_commit>
- Target: <review bundle生成時点のworktreeと対象パス>
- Acceptance criteria: <Workが照合する条件>
- Review bundle: <bundle名、SHA-256、sidecar>
- Focus: <重点確認事項>

Workへの依頼：
INDEX、DIFF_INDEX、SKIPPED、MANIFESTを先に確認してください。
Base HEADに対するTargetだけをread-onlyでレビューし、
仕様適合、変更漏れ、副作用、対象外差分、文書同期、試験を判定してください。
結果は次の構造で、対象bundleを特定する外部レビュー証跡として返してください。

work_review:
  status: <approved | changes_requested>
  evidence: <bundle名、SHA-256、レビュー根拠>
```

`approved`ならUserのstage／commit判断へ進む。
`changes_requested`なら番号付き修正事項をCodexへ戻す。
Workは承認結果を記録するためにチェックポイントを編集しない。

## D. thread／taskを引き継ぐ

```markdown
# <project> handoff

- Checkpoint: `<handoff/current.md>`
- Codex target evidence: <最終報告とreview bundle>
- Work review evidence: <対象bundle付き結果 or pending>
- User evidence: <commit／push結果 or pending>
- Repository facts: <branch / HEAD / status / remote>
- Effective state: <上記証跡から復元した現在状態>
- Next single action: <一作業>

引き継ぎ先への依頼：
実リポジトリの事実を優先し、同じreview targetへ結び付く証跡から状態を復元して、
Next single actionだけを開始してください。
```

引き継ぎ文には現在有効な証跡と次の一作業だけを残す。
完了実況、非実施履歴、過去bundle一覧、共通ルール全文は蓄積しない。
bundle生成の選択と工程遷移は`shared/01_ai_consult_procedures.md`を参照する。
