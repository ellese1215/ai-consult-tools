# 03 ChatGPTセッション開始ガイド

> **旧版資料**
>
> 本書はV4-6まで保持する旧モデル別スクリプト用資料です。現行共通CLIの正本ではありません。
> 現行の利用方法は`../README.md`、技術仕様は`../docs/01_current_spec.md`、運用ルールは`../shared/00_ai_consult_operation_rules.md`を参照してください。

> File: 03_chatgpt_session_guide.md
> Version: 1.1.0
> Updated: 2026-06-26

このファイルは、ChatGPTとの相談セッションを正しく開始するための手順と、モード選択の判断基準を説明します。

---

## 1. セッション開始の基本手順

### ステップ1：include bundleを生成する

相談内容に応じて必要なファイルをincludeモードで抽出します。定型の相談では `--include-set` を優先して使います。

```powershell
cd C:\xampp\htdocs
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py `
  --mode include `
  --repo-root "C:\xampp\htdocs" `
  --case-name "<相談名>" `
  --include-set "common_rules" `
  --include-paths `
    "<対象ファイルのパス>"
```

相談基盤の見直しでは、たとえば次のように生成します。

```powershell
cd C:\xampp\htdocs
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py `
  --mode include `
  --repo-root "C:\xampp\htdocs" `
  --case-name "consult_tools_review" `
  --include-set "chatgpt_tool_core"
```

生成された ZIP ファイルをChatGPTのチャットに添付します。ZIP内の `PATH_INDEX.md` と `SKIPPED.txt` で、指定パスの実在確認・不足・除外を確認できます。

### ステップ2：指示文を送る

以下の指示文を添付とともに送ります（`02_consult_template_chatgpt.md` の冒頭にコピー用があります）。

```
添付のinclude bundleを唯一の正として参照確定してください。
`00_ai_consult_operation_rules.md` の最新バージョンに従い、以下の順で宣言してから作業を開始してください。

1. 運用ルール認識完了を宣言する
2. 添付bundle内のドキュメントを読み、現在の相談内容を確認・宣言する
3. 引き継ぎ情報がある場合はその内容から作業を開始する
```

### ステップ3：ChatGPTの参照確定宣言を確認する

ChatGPTが以下を宣言してから作業を始めることを確認してください：

1. 運用ルール認識完了
2. 相談内容の確認・宣言
3. `PATH_INDEX.md` / `SKIPPED.txt` の確認
4. 引き継ぎ情報の確認（ある場合）

宣言なしに作業を始めた場合は、宣言を求めてください。

---

## 2. モード選択の判断基準

| やりたいこと | 使うモード |
|---|---|
| まずリポジトリ全体の構造を把握したい | **map** |
| 特定のファイル・フォルダの内容をChatGPTに見せたい | **include** |
| 修正後の変更内容をレビューしたい | **diff** |
| リポジトリ全体を横断的に参照させたい | **repo** |

### 基本方針

```
要求 → map（構造把握） → include（本文根拠の固定） → 仕様案 → 合意 → 実装 → diff（レビュー） → commit → push
```

- **定型相談はinclude setから始める**：既知の相談種別は `--include-set` を使う
- **パス不明時はmapから始める**：AIがパスを推測しない
- **includeは必要最小限に**：ChatGPTに読ませるファイルを絞ることで精度が上がる
- **修正後は必ずdiff**：変更内容・副作用を根拠付きで確認する
- **repoは最後の手段**：mapで足りないときだけ使う

各モードの詳細は `01_make_consult_bundle_spec_chatgpt.md` を参照してください。

---

## 3. よく使うincludeコマンドパターン

### 共通ルール + 個別対象

```powershell
cd C:\xampp\htdocs
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py `
  --mode include `
  --repo-root "C:\xampp\htdocs" `
  --case-name "<相談名>" `
  --include-set "common_rules" `
  --include-paths `
    "<対象ファイル>"
```

### ChatGPT相談基盤メンテ

```powershell
cd C:\xampp\htdocs
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py `
  --mode include `
  --repo-root "C:\xampp\htdocs" `
  --case-name "consult_tools_review" `
  --include-set "chatgpt_tool_core"
```

### include set + 追加ファイル

```powershell
cd C:\xampp\htdocs
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py `
  --mode include `
  --repo-root "C:\xampp\htdocs" `
  --case-name "config_check" `
  --include-set "chatgpt_tool_core" `
  --include-paths `
    "追加で確認したいファイル"
```

### パス不明時のmap

```powershell
cd C:\xampp\htdocs
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py `
  --mode map `
  --repo-root "C:\xampp\htdocs" `
  --case-name "path_check"
```

mapで所在を確認してから、include set または明示パスで include bundle を作成します。

---

## 4. diffレビューの手順

修正を適用した後は以下の手順でdiff bundleを生成してChatGPTに添付します。

```powershell
# 未コミット差分（適用直後）
cd C:\xampp\htdocs
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py `
  --mode diff `
  --repo-root "C:\xampp\htdocs" `
  --case-name "<相談名>"

# staged差分（git add後）
cd C:\xampp\htdocs
python .\ai-consult-tools\chatgpt\consult_bundle_chatgpt.py `
  --mode diff `
  --repo-root "C:\xampp\htdocs" `
  --case-name "<相談名>" `
  --staged
```

ChatGPTは diff bundle を受け取ったら以下を確認します：

- 変更対象ファイルが意図通りか
- 変更内容に漏れ・過不足がないか
- 今回対象外のファイルへの副作用がないか

---

## 5. セッション終了時の手順

1. スレッド内の作業内容を整理する
2. TODOドキュメントを更新する（`00_ai_consult_operation_rules.md` 12章に従う）
3. 作業コードの修正とTODO更新をまとめてcommit → pushする
4. 引き継ぎ文をChatGPTに作成させる（`02_consult_template_chatgpt.md` セクション11に記録）
5. 次スレッドへの引き継ぎ文をコピーして保管する

---

## 6. Blocking Questions（BQ）について

ChatGPTが作業中に不明点を「Blocking Questions（BQ）」として提示した場合：

- BQに回答してから作業を再開させてください
- 「おそらくこうだろう」で進めさせないでください
- 必要であれば追加のinclude bundleを生成して根拠を提示してください

---

## 7. よくある操作ミスと対処

| 問題 | 対処 |
|---|---|
| `python` コマンドが見つからない | `python3` で代替する。または Python 3.9+ がインストールされているか確認する |
| `consult_bundle_chatgpt.py` が見つからないと言われる | カレントディレクトリを確認する。スクリプトのパスを絶対パスで指定する |
| 同名ファイルが複数ヒットしてエラーになった | `PATH_INDEX.md` の候補を確認し、`--include-paths` にフルパス（相対パス）で指定する |
| diff modeで差分が0件だった | 変更が未保存か、すでにコミット済みの可能性がある |
| 出力ZIPが生成されない | `--repo-root` のパスとカレントディレクトリを確認する |
| `SKIPPED.txt` が `(none)` ではない | missing / excluded が意図通りか確認し、必要ならパスや include set を修正する |
| `consult.config_chatgpt.json` が見つからないと言われる | `consult.config.example_chatgpt.json` をコピーして `local/chatgpt/consult.config_chatgpt.json` を作成する |
