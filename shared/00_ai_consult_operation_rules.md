# AI相談 最上位運用契約

> File: `shared/00_ai_consult_operation_rules.md`
> Updated: 2026-07-24
> Workflow schema: `ai-consult-workflow/v1`

## 1. 契約の要点

本書は、Work、Codex、UserがGit管理対象を変更するときの最上位契約である。
変更の種類や規模にかかわらず、次のゲートを順に通す。

```text
Work仕様確定
→ Codex変更・試験・チェックポイント作成
→ Work独立レビュー
→ Userのstage／commit判断
→ Userのpush判断と必要なremote照合
```

- Workはread-only調査、仕様確定、進行管理、Codexへの限定指示、Codex差分・試験の独立レビュー、完了判定を担う。
- Codexは実リポジトリ調査、Git管理対象の編集、文書同期、試験、変更証跡作成、Git内チェックポイント作成を担う。
- Userは方針承認、stage、commit、push、DB適用や公開など外部状態変更の判断を担う。

Workレビューゲートは、Codex証跡と同じreview targetへのWork承認がそろった時点で完了する。
現在担当、次担当、許可操作、未完了ゲートを証跡から復元できない場合は、次工程へ進まない。

## 2. 正本とチェックポイント

branch、HEAD、status、remoteの事実は、ローカルの現行Gitリポジトリを正本とする。
bundleは生成時点の参照またはレビュー資料であり、恒久的な仕様正本ではない。

| 判断対象 | 主な根拠 |
|---|---|
| 最上位の役割とゲート | 本書 |
| Git内の最新工程チェックポイント | `docs/handoff/current.md`または各プロジェクトの`handoff/current.md` |
| 詳細な受渡しと遷移 | `shared/01_ai_consult_procedures.md` |
| 状態schemaと依頼書式 | `shared/02_consult_template.md` |
| CLIとbundleの技術契約 | `docs/01_current_spec.md`と現行コード |
| ローカル環境 | `local/consult.local.md` |
| 機密情報の取扱い | `shared/SECURITY.md` |
| 仕様と実装事実 | 要件書、設計書、現行コード、試験、必要に応じて実DB |

`handoff/current.md`は、Codexがreview targetをWorkへ渡す時点で作成するGit内の最新工程チェックポイントである。
Base、変更範囲、Codex証跡、次のゲートを記録し、後続結果を常時反映するlive stateにはしない。
Work承認、commit、pushだけを記録するための単独Git変更を要求しない。

## 3. 有効な工程状態の復元

有効な工程状態は、次を同じreview targetへ結び付けて復元する。

1. 最新のCodex作成チェックポイント
2. review targetを特定したCodex最終報告とreview bundle
3. 対応する最新のWorkレビュー結果
4. Userが提示したstage／commit／push結果
5. 実リポジトリのbranch、HEAD、status、remote照合結果

実リポジトリの事実を最優先し、Work承認は対象bundleを特定した最新結果、commit／pushはUserのコマンド結果と実リポジトリ照合を優先する。
チェックポイントはBase、変更範囲、Codex証跡、次ゲートの基準として扱う。
証跡同士を同じreview targetへ結び付けられない場合、または証跡が矛盾する場合は次工程へ進まない。

`base_commit`はreview targetを作成した基準HEADとして固定する。
Work承認、commit、pushでは上書きせず、commit結果は`result_commit`、remote照合結果は`remote_commit`で扱う。
新たな実質的変更サイクルを開始するときだけ、開始前HEADから新しい`base_commit`を設定する。

## 4. Work仕様確定

Workは実装前にread-onlyで次を確定する。

1. 目的と受入条件
2. 基準branch、Base HEAD、参照DocSet
3. 対象パスと保護対象
4. 確定仕様と未確定事項
5. Codexに許可する操作
6. 必要な文書同期と試験
7. Workレビューの重点

確定後は、Codexが一作業として実行できる限定指示を外部の依頼証跡として渡す。

## 5. Codex変更・試験

Codexは編集前にRepoRoot、branch、HEAD、worktree、対象パス、保護対象を実確認する。
対象内に想定外の変更がある場合、または対象外差分と安全に分離できない場合は編集を開始しない。

Codexは確定仕様、変更、正本文書、試験を同じ作業単位でそろえる。
変更後はBase HEAD、変更パス、試験、差分検査、保護対象を`codex_evidence`へ記録する。
Workへ渡す前にチェックポイントとreview bundleを同じreview targetの一部として作成する。

## 6. Work独立レビュー

Workはチェックポイント、Codex最終報告、Base HEADに対する実差分、review bundle、試験証跡をread-onlyで確認する。
Workは承認のためにGit管理ファイルを編集せず、bundle名とSHA-256などでreview targetを一意に特定した外部レビュー結果を返す。

- `changes_requested`なら番号付き修正事項をCodexへ戻し、新しい実質的変更サイクルを開始する。
- `approved`ならチェックポイント同期を挟まず、Userのstage／commit判断へ進む。

修正時はCodexが新しいチェックポイントとreview bundleを作り、Workが最新targetを再レビューする。

## 7. User判断

Work承認後、Userがstage／commitを判断し、結果は外部報告と実リポジトリ照合で保持する。
commit完了後はチェックポイント同期を挟まず、Userがpushを別に判断する。
push後は必要なremote照合を行い、同じreview targetに結び付く外部証跡として扱う。

状態同期だけを目的としてCodexへ戻さない。
新たな実質的変更が必要な場合だけ、実リポジトリを再確認して新しいCodex変更サイクルを開始する。

## 8. 事故防止

- APIキー、パスワード、トークン、秘密鍵、不要な個人情報を文書やbundleへ収録しない。
- `git clean`、`git reset --hard`など、対象外差分を失う破壊的Git操作を実行しない。
- 対象外変更を編集、削除、復元、stash、stage、commitしない。
- 不正または不明なbase／targetではレビューを承認しない。
- Work承認とUser判断をCodex自身の判断で置き換えない。

## 9. 完了条件

Workレビューゲートの完了条件：

- Codex変更・試験証跡がreview targetと一致する
- 同じreview targetを一意に特定したWork承認がある

変更工程全体の完了条件：

- Workレビューゲートが完了している
- Userのcommit判断と結果が確認されている
- 必要なpush判断とremote照合が完了している
- 対象外差分が保護され、証跡間に矛盾がない

Work承認はGitファイルへの追記がなくても有効である。
具体的なbundle生成、遷移、Git前後確認、thread立て直しは`shared/01_ai_consult_procedures.md`を参照する。
