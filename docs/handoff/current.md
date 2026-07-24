# AI相談運用改修 最新工程チェックポイント

このファイルは、Codexがreview targetをWorkへ渡す時点で作成するGit内の最新工程チェックポイントである。
Work承認、commit、pushの後続結果を常時反映するlive stateではない。

```yaml
workflow_schema: ai-consult-workflow/v1
case: ai_consult_work_codex_gate_and_docs_compaction
base_branch: master
base_commit: 2153db0425dd4c68543ae22cd723f2b4c707b9c4
source_docset: 20260724170609
current_phase: document model correction review
current_gate: work independent re-review
current_actor: Work
next_actor: User（承認時。修正要求時はCodexへ戻す）
allowed_operations:
  - D-1 review bundleと今回のcorrection review bundleを用いたread-onlyレビュー
pending_gates:
  - Work独立再レビュー
  - ユーザーのstage／commit判断
  - ユーザーのpush判断
  - 後続の機械的ゲート実装要否判断
codex_evidence:
  base_commit: 2153db0425dd4c68543ae22cd723f2b4c707b9c4
  d1_changed_paths:
    - ai-consult-tools/README.md
    - ai-consult-tools/config/consult.config.example.json
    - ai-consult-tools/docs/01_current_spec.md
    - ai-consult-tools/docs/handoff/current.md
    - ai-consult-tools/local/consult.config.json
    - ai-consult-tools/local/consult.local.md
    - ai-consult-tools/local/runbooks/ai_consult_tools_publish.md
    - ai-consult-tools/shared/00_ai_consult_operation_rules.md
    - ai-consult-tools/shared/01_ai_consult_procedures.md
    - ai-consult-tools/shared/02_consult_template.md
    - ai-consult-tools/shared/consult.local.example.md
    - ai-consult-tools/tests/test_config.py
    - ai-consult-tools/tests/test_operation_docs.py
  correction_changed_paths:
    - ai-consult-tools/shared/00_ai_consult_operation_rules.md
    - ai-consult-tools/shared/01_ai_consult_procedures.md
    - ai-consult-tools/shared/02_consult_template.md
    - ai-consult-tools/docs/handoff/current.md
    - ai-consult-tools/tests/test_operation_docs.py
  tests:
    - D-1 review bundleと13対象の開始前照合: passed
    - test_operation_docs.py: passed（18 tests）
    - ai-consult-tools全試験: passed（259 tests、3 skipped）
    - D-1の変更対象外8ファイル照合: passed
  diff_check: passed（今回5対象、ai-consult-tools全体）
  protected_changes:
    - folder_tree.txt（D-1開始前から変更済みのため未編集、structure sync保留）
work_review:
  status: pending
  evidence: null
user_decisions:
  policy:
    - すべてのGit管理対象変更でWork→Codex→Workを必須化
    - handoff/current.mdをCodex作成のGit内工程チェックポイントとして使用
    - 文書モデル確定後に機械的ゲートを別工程で検討
  commit:
    status: pending
    result_commit: null
    evidence: null
  push:
    status: pending
    remote_commit: null
    evidence: null
next_single_action: 今回のcorrection review bundleを、D-1 review bundleと合わせてWorkが独立再レビューする
```

Workレビュー結果とUser操作結果は、対象review bundleを特定した外部証跡と実リポジトリ照合で保持する。
`base_commit`はこのreview targetの基準HEADとして固定し、commit結果は`result_commit`、remote照合結果は`remote_commit`で扱う。
今回のcorrection review bundle名とSHA-256はINDEXとCodex最終報告へ記録し、このファイルには書かない。
