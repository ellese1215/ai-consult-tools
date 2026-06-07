# 03 Claudeセッション開始ガイド

> File: 03_claude_session_guide.md
> Version: 2.0.0
> Updated: 2026-06-07

このファイルは、Claudeとの相談セッションを正しく開始するための手順と、モード選択の判断基準を説明します。

---

## 1. セッション開始の基本手順

### ステップ1：include bundleを生成する

相談内容に応じて必要なファイルをincludeモードで抽出します。`consult.local.md` が存在する場合は必ず含めてください。

```bash
cd <your-repo>; python consult_bundle_claude.py \
  --mode include \
  --repo-root <your-repo> \
  --case-name "<相談名>" \
  --include-paths \
    "ai-consult-tools/claude/00_ai_consult_operation_rules.md" \
    "ai-consult-tools/claude/consult.local.md" \
    "<対象ファイルのパス>"
```

生成された `.md` ファイルをClaudeのチャットに添付します。

### ステップ2：指示文を送る

以下の指示文を添付とともに送ります（`02_consult_template.md` の冒頭にコピー用があります）。

```
添付のinclude bundleを唯一の正として参照確定してください。
`00_ai_consult_operation_rules.md` の最新バージョンに従い、以下の順で宣言してから作業を開始してください。

1. 運用ルール認識完了を宣言する
2. 添付bundle内のドキュメントを読み、現在の相談内容を確認・宣言する
3. 引き継ぎ情報がある場合はその内容から作業を開始する
```

### ステップ3：Claudeの参照確定宣言を確認する

Claudeが以下を宣言してから作業を始めることを確認してください：

1. 運用ルール認識完了
2. 相談内容の確認・宣言
3. 引き継ぎ情報の確認（ある場合）

宣言なしに作業を始めた場合は、宣言を求めてください。

---

## 2. モード選択の判断基準

| やりたいこと | 使うモード |
|---|---|
| まずリポジトリ全体の構造を把握したい | **map** |
| 特定のファイル・フォルダの内容をClaudeに見せたい | **include** |
| 修正後の変更内容をレビューしたい | **diff** |
| リポジトリ全体を横断的に参照させたい | **repo** |

### 基本方針

```
要求 → map（構造把握） → include（本文根拠の固定） → 仕様案 → 合意 → 実装 → diff（レビュー） → commit → push
```

- **最初はmapから始める**：いきなり大量のファイルをincludeしない
- **includeは必要最小限に**：Claudeに読ませるファイルを絞ることで精度が上がる
- **修正後は必ずdiff**：変更内容・副作用を根拠付きで確認する
- **repoは最後の手段**：mapで足りないときだけ使う

各モードの詳細は `01_make_consult_bundle_spec.md` を参照してください。

---

## 3. よく使うincludeコマンドパターン

### 運用ルールのみ（基盤メンテ時）

```bash
cd <your-repo>; python consult_bundle_claude.py \
  --mode include \
  --repo-root <your-repo> \
  --case-name "base_maint" \
  --include-paths \
    "ai-consult-tools/claude/00_ai_consult_operation_rules.md" \
    "ai-consult-tools/claude/consult_bundle_claude.py"
```

### 特定フォルダ + 運用ルール

```bash
cd <your-repo>; python consult_bundle_claude.py \
  --mode include \
  --repo-root <your-repo> \
  --case-name "auth_feature" \
  --include-paths \
    "ai-consult-tools/claude/00_ai_consult_operation_rules.md" \
    "src/auth"
```

### 複数ファイル指定

```bash
cd <your-repo>; python consult_bundle_claude.py \
  --mode include \
  --repo-root <your-repo> \
  --case-name "config_check" \
  --include-paths \
    "ai-consult-tools/claude/00_ai_consult_operation_rules.md" \
    "src/Config.php" \
    "src/Router.php"
```

---

## 4. diffレビューの手順

修正を適用した後は以下の手順でdiff bundleを生成してClaudeに添付します。

```bash
# 未コミット差分（適用直後）
cd <your-repo>; python consult_bundle_claude.py \
  --mode diff \
  --repo-root <your-repo> \
  --case-name "<相談名>"

# staged差分（git add後）
cd <your-repo>; python consult_bundle_claude.py \
  --mode diff \
  --repo-root <your-repo> \
  --case-name "<相談名>" \
  --staged
```

Claudeは diff bundle を受け取ったら以下を確認します：

- 変更対象ファイルが意図通りか
- 変更内容に漏れ・過不足がないか
- 今回対象外のファイルへの副作用がないか

---

## 5. セッション終了時の手順

1. スレッド内の作業内容を整理する
2. 修正をcommit → pushする
3. 引き継ぎ文をClaudeに作成させる（`02_consult_template.md` セクション11に記録）
4. 次スレッドへの引き継ぎ文をコピーして保管する

---

## 6. Blocking Questions（BQ）について

Claudeが作業中に不明点を「Blocking Questions（BQ）」として提示した場合：

- BQに回答してから作業を再開させてください
- 「おそらくこうだろう」で進めさせないでください
- 必要であれば追加のinclude bundleを生成して根拠を提示してください

---

## 7. よくある操作ミスと対処

| 問題 | 対処 |
|---|---|
| `python` コマンドが見つからない | `python3` で代替する。または Python 3.9+ がインストールされているか確認する |
| `consult_bundle_claude.py` が見つからないと言われる | カレントディレクトリを確認する。スクリプトのパスを絶対パスで指定する |
| 同名ファイルが複数ヒットしてエラーになった | `--include-paths` にフルパス（相対パス）で指定する |
| diff modeで差分が0件だった | 変更が未保存か、すでにコミット済みの可能性がある |
| 出力が `_part1.md` / `_part2.md` に分割された | 両方のファイルをClaudeに添付する |
| `consult.config.json` が見つからないと言われる | `consult.config.example.json` をコピーして `consult.config.json` を作成する |
