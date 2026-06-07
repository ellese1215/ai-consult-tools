# 02 Claude相談テンプレート

> File: 02_consult_template.md
> Version: 2.0.0
> Updated: 2026-06-07

このファイルは、Claudeへの相談スレッドを開始するときのテンプレートです。
セクション番号はスレッド内で管理する番号です。適宜追記・更新してください。

---

## スレッド開始時のClaudeへの指示文（コピー用）

スレッドを開始するときは、以下の指示文とともにinclude bundleを添付してください。

```
添付のinclude bundleを唯一の正として参照確定してください。
`00_ai_consult_operation_rules.md` の最新バージョンに従い、以下の順で宣言してから作業を開始してください。

1. 運用ルール認識完了を宣言する
2. TODOドキュメント（添付のinclude bundle内）を読み、現在どのPhaseの相談かを確認・宣言する
3. 引き継ぎ情報を読んだ上で、残課題・次の相談内容から作業を開始する
```

---

## スレッド開始時のincludeコマンド（例）

```bash
cd <your-repo>; python ai-consult-tools/claude/consult_bundle_claude.py --mode include --repo-root <your-repo> --case-name "<相談名>" --include-paths "ai-consult-tools/shared/00_ai_consult_operation_rules.md" "<対象ファイルのパス>"
```

---

## 1. 相談概要

- **相談日**：
- **相談内容**：
- **関連Phase / タスク**：

---

## 2. 参照確定

- **Include DocSet**：
- **Diff DocSet**：
- **根拠ファイル**：

---

## 3. Blocking Questions（未解消の確認事項）

未解消のBQがあればここに記載します。

- BQ1：
- BQ2：

---

## 4. 仕様案

Claudeが提示した仕様案を記録します。

---

## 5. 合意内容

ユーザーが承認した内容を記録します。

---

## 6. 実装内容

Claudeが生成したスクリプト・コード・SQLの概要を記録します。

---

## 7. 差分レビュー結果

Diff bundleのDocSetとレビュー結果を記録します。

- **Diff DocSet**：
- **変更ファイル**：
- **判定**：OK / NG

---

## 8. コミット情報

- **コミットハッシュ**：
- **コミットメッセージ**：

---

## 9. 試験結果

試験項目と結果を記録します。

---

## 10. 残課題

このスレッドで解消できなかった課題を記録します。

---

## 11. 次スレッドへの引き継ぎ文

スレッド終了時にClaudeが作成する引き継ぎ文をここに記録します。

```
（Claudeが作成）
```
