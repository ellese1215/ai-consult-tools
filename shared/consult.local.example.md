# consult.local.md

> File: `local/consult.local.md`
> `shared/consult.local.example.md`をコピーして作るGit管理外文書。

秘密情報、一時的な工程状態、完了履歴、案件固有の長い公開コマンドは記載しない。

## 1. 環境

| 項目 | 値 |
|---|---|
| RepoRoot | `<absolute-repo-root>` |
| OS | `<Windows / macOS / Linux>` |
| Shell | `<shell and version>` |

## 2. Shell安全規則

環境に合う値へ置き換える。

- stop-on-error設定：`<setting>`
- strict modeまたは同等設定：`<setting>`
- 一括コピー単位：`<one executable unit>`
- 外部スクリプトの安全な文字コード：`<encoding>`
- 外部スクリプトの構文確認：`<parser command>`
- 実行前に示す情報：RepoRoot、前提、対象パス
- 実行後に確認する情報：終了コードと成功出力
- 状態変更の区切り：stage、commit、push、deployを分ける
- `.Count`参照：生成式またはパイプライン全体を配列化する
- native command：直後に終了コードを確認する
- 単一行出力：配列化し、1件かつ空でないことを確認して読む
- プレースホルダー：書式例だけで使い、実行用コマンドには残さない

## 3. プロジェクト別主要コマンド

標準bundleで次の担当が必要とするbuild、test、静的解析だけを記載する。

```text
<profile-name>:
  build: <command or none>
  test: <command or none>
  manual_check: <procedure or none>
```

長いdeploy、remote追加、push、subtree手順は第5章のrunbookへ分離する。

## 4. bundle区分

通常のプロジェクト引き継ぎ：

```text
--include-set common_rules
+ 案件ごとのhandoff/current.mdと必要資料
```

AI相談ツール自体の保守：

```text
--include-set common_rules
--include-set ai_consult_maintenance
+ ai-consult-tools/docs/handoff/current.md
+ 作業対象
```

`common_rules`には最上位契約、共通工程テンプレート、このlocal文書だけを含める。
CLIの正確な書式と出力契約は`ai-consult-tools/docs/01_current_spec.md`を参照する。

## 5. 詳細runbook

標準bundleで常時不要な長い操作は、Git管理外のファイルへ分離する。

```text
ai-consult-tools/local/runbooks/<topic>.md
```

runbookには用途、前提、対象、承認境界、完全なコマンド、成功確認、停止条件を記載する。
runbookは必要なときだけ読み、`common_rules`へ含めない。

## 6. 維持方針

現在も有効で、将来の操作または判断を変えるローカル情報だけを残す。
一時状態は案件の`handoff/current.md`、未完了作業はTODO、決定履歴は適切な履歴文書で管理する。
