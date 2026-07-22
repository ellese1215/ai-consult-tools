# AI相談用・最小テンプレート

> File: `shared/02_consult_template.md`
> Updated: 2026-07-22
> Rules revision: 20260722-simplified-r2

必要な形式を一つだけ選び、空欄と不要な項目は削除する。

## A. Workで仕様を確定する

```markdown
# <project> <topic>

- Purpose: <今回確定する一つの結果>
- Current source: <branch / commit / start bundle>
- Current state: <必要最小限>
- Decisions needed: <確定事項>
- Invariants: <変えてはいけないこと>
- Out of scope: <対象外>

Workへの依頼：実装仕様、対象、対象外、受入条件、文書更新、想定テストを確定してください。不明点が結果を変える場合だけ質問してください。
```

リポジトリを読めないWorkに限り、最新start bundle一つを添付する。

## B. Codexへ実装を依頼する

```markdown
# <project> <implementation unit>

- Repo root: <path>
- Expected branch / base: <value>
- Purpose: <一文>
- Confirmed requirements: <仕様>
- Target: <対象>
- Protected / out of scope: <既存変更・対象外>
- Acceptance criteria: <正常・異常・境界の該当項目>
- Required docs and tests: <対象>

開始時にリポジトリ、HEAD、worktree、共通ルール、プロジェクトREADME、status、todo、handoff、対象仕様を確認し、実装・文書同期・試験まで行ってください。
```

Codexがリポジトリを読める場合はbundleを添付しない。読めない場合だけ最新start bundle一つを添付する。

## C. Workへ実装レビューを依頼する

```markdown
# <project> implementation review

- Base HEAD: <commit>
- Target state: <review bundle名 / worktree状態>
- Review bundle: <latest bundle>
- Requirements / acceptance criteria: <条件>
- Focus: <重点確認事項>

最初に`DIFF_INDEX.md`、`SKIPPED.md`、`MANIFEST.csv`を確認してください。skipまたは収録不足が結論に影響する場合は承認せず、不足を番号付き修正事項として示してください。Base HEADに対するTarget stateだけをレビューし、問題がなければ「承認」、問題があれば同じCodexへ戻せる番号付き修正事項を提示してください。
```

最新review bundle一つだけを添付する。start bundle、旧review bundle、通常ログは添付しない。

## D. 新しいスレッドへ引き継ぐ

```markdown
# <project> handoff

- Current phase: <phase>
- Branch / commit: <value>
- Completed: <完了範囲>
- Next single task: <次の一作業>
- Target docs / code: <対象>
- Protected / out of scope: <対象外>
- Open issues: <なければ「なし」>
- Only attached artifact: <なければ「なし」>

## Bundle generation command

<bundleが必要な場合だけ、実在するprofile・case・対象パスを指定したPowerShell全文>
```

収録対象と標準コマンドは共通運用ルール第4章に従う。過去bundle一覧、共通ルール全文、完了作業の長いログは転記しない。
