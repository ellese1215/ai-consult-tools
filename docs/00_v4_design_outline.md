# AI相談運用基盤 v4 設計骨子

## 1. 目的

既存のv3.1.5へ機能を継ぎ足すのではなく、ChatGPT版とClaude版を共通コアへ統合し、v4として再設計する。

共通化する対象は以下とする。

- ファイル収集
- パス解決
- 除外判定
- テキスト・バイナリ判定
- manifest
- diff
- 構造インベントリ
- プロジェクト単位の対象範囲
- 検証処理

モデルごとの差は、最終的な出力形式だけに限定する。

bundleは正本ではなく、生成時点の参照スナップショットとして扱う。

---

## 2. V4-0 現状固定結果

### 2.1 ライブrepo

確認日時は2026年7月10日。

RepoRootは以下である。

```text
C:\xampp\htdocs
```

主要ルートとして以下が存在する。

```text
ai-consult-tools/
apps/
common/
db/
docs/
packages/
pavilion-ellese/
```

### 2.2 `ai-consult-tools`の状態

入れ子の`.git`内部を除く実在ファイルは36件。

| 区分 | 件数 |
|---|---:|
| tracked | 19 |
| untracked | 1 |
| ignored | 16 |

Git状態は以下である。

- trackedファイルのunstaged差分：なし
- staged差分：なし
- 未追跡：`ai-consult-tools/docs/00_v4_design_outline.md`
- Git管理されたsymlink：なし

ignoredファイルには以下が含まれる。

- `archive/`の旧版
- ChatGPT・Claudeの生成済みbundle
- `local/`の実設定

`ai-consult-tools/.git/`も実在するが、用途は現時点で確定していない。削除はせず、構造走査、bundle生成、clean exportから除外する。

### 2.3 既存構造ファイル

| ファイル | 状態 | v4での扱い |
|---|---|---|
| `folder_tree.txt` | 2026年4月24日更新、UTF-16LE、約1.39MB | 全面再生成して構造正本として再利用 |
| `tree.txt` | 2026年4月26日更新、UTF-16LE、約1.39MB | V4-6で削除 |
| `duplicate_filenames_report.md` | 2026年5月8日更新、約469KB | V4-6で削除 |

tracked文書から参照されているのは`folder_tree.txt`だけである。

参照元は以下。

- `docs/projectFiles/エリーゼの館/04_decision_log.md`
- `docs/projectFiles/エリーゼの館/05_docs_index_governance.md`

`tree.txt`と`duplicate_filenames_report.md`へのtracked文書からの参照は確認されなかった。

---

## 3. v4の基本原則

- 現行v3.1.5への継ぎ足しではなく、v4として再設計する
- ChatGPT版とClaude版で共通コアを使用する
- 機械的に検証可能な規則はコードとテストへ移す
- 要求仕様、設計、実装・実DB、進捗・保留を別の根拠として扱う
- 既存文書で扱える内容について類似文書を増やさない
- 現行仕様と過去の判断履歴を混在させない
- 用途、利用者、呼び出し元を説明できない機能を追加しない
- 保留項目には目的、理由、再開条件、最初の作業を残す
- TODOや引き継ぎ文へ会話履歴を蓄積し続けない
- 作業リスクをL1からL3に分類する

---

## 4. v3.1.5で確認された問題

### 4.1 パスと安全性

- RepoRoot外の絶対パスをincludeできる
- RepoRoot外を指すsymlink経由で内容を取得できる
- `..`や実体解決後の境界確認が統一されていない
- バイナリ判定がない
- UTF-16ファイルをUTF-8として破損読込する

### 4.2 収集と除外

- パス付き除外設定がdiffで機能しない
- ルート直下の`shared/`がハードコードで除外される
- Claude版で明示include対象が黙って省略される場合がある
- 構造インベントリと本文収録対象の除外規則が混在している
- 巨大ファイルを中央省略したまま参照資料として扱う
- 同一ルール文書をZIP直下とsnapshot内へ二重収録する

### 4.3 diff

- 未追跡ファイルがstage前のdiffに入らない
- diff対象パスを限定できない
- 標準diffが無関係なunstaged変更まで含める

### 4.4 出力と再現性

- Claude版に未置換プレースホルダーが残る
- Claude版にPATH_INDEX・SKIPPED相当がない
- Claude版の記録コマンドをそのまま再実行できない
- ChatGPT版とClaude版のコード重複によって機能差が生じている
- ファイル本文のMarkdownフェンスによってsnapshotが壊れる可能性がある
- ZIP生成失敗時にも成功終了する場合がある
- 同じ出力先を事前清掃せず、以前の生成物が混入する可能性がある
- 曖昧パスの候補提示と処理継続方針が統一されていない
- snapshot読込失敗時に件数表示とmanifestが一致しない可能性がある
- bundleを「唯一の正」とする文言が、時点スナップショットという位置づけと矛盾する

これらは運用ルールを増やして回避せず、共通コードと自動テストで解消する。

---

## 5. 共通アーキテクチャ

```text
CLI
 ├─ 共通設定
 ├─ パス解決
 ├─ 除外判定
 ├─ 構造インベントリ
 ├─ Git差分収集
 ├─ bundleモデル生成
 └─ 出力アダプター
      ├─ ChatGPT ZIP
      └─ Claude Markdown
```

収集結果を共通の内部モデルとして保持し、モデル別レンダラーへ渡す。

ChatGPT版とClaude版で別々にファイルを走査しない。

---

## 6. 構造管理

### 6.1 `folder_tree.txt`

既存の`folder_tree.txt`を構造正本として再利用する。

v4移行時に旧Windows `tree`形式を破棄し、以下の形式で全面再生成する。

```text
文字コード：UTF-8 BOMなし
改行：LF
パス：RepoRoot相対
区切り：/
内容：フォルダとファイルのパスのみ
並び：決定的ソート
更新：構造が変わった場合だけ
手動編集：禁止
```

更新日時、ハッシュ、Git状態は`folder_tree.txt`へ入れない。

### 6.2 ローカルインデックス

機械可読情報は以下へ保存する。

```text
ai-consult-tools/local/cache/repo_structure_index.json
```

V4-2C時点の最小スキーマは以下。

```json
{
  "schemaVersion": 1,
  "entries": [
    {
      "relativePath": "ai-consult-tools/src/ai_consult/inventory.py",
      "name": "inventory.py",
      "parentPath": "ai-consult-tools/src/ai_consult",
      "entryType": "file",
      "linkType": "none",
      "extension": ".py"
    }
  ]
}
```

出力条件は以下。

- UTF-8 BOMなし
- LF
- 2スペースインデント
- 末尾LFあり
- `entries`は構造走査結果と同じ決定的順序
- キー順固定
- 生成日時と絶対RepoRootは収録しない

プロジェクト所属は`relativePath`とプロジェクトプロファイルを組み合わせて判定し、インデックスへ重複保存しない。

Git追跡状態と本文収録可能判定は、Git差分・bundle収集へ接続するV4-3で追加を検討する。

ローカルインデックスはGit管理しない。

### 6.3 構造と本文収録の分離

構造インベントリには画像、音声、フォント、ZIPなどもパスとして記録できる。

AIへ本文を渡す対象は、判定済みのテキストファイルに限定する。

完全除外対象は別に管理する。

主な完全除外対象は以下。

- `.git/`
- `node_modules/`
- `vendor/`
- build生成物
- consult生成物
- secrets
- ローカル専用設定
- 明示された非公開物

symlinkとjunctionはパスを記録できるが、リンク先へ再帰しない。

---

## 7. プロジェクトプロファイル

プロジェクトごとの対象範囲をローカル設定で管理する。

```json
{
  "schemaVersion": 1,
  "profiles": {
    "pavilion_ellese": {
      "scopeRoots": [
        "apps/webs/pavilion-ellese",
        "pavilion-ellese/Resources",
        "common/Config/pavilion-ellese",
        "common/src/App",
        "packages/ts/web",
        "packages/styles/web/pavilion-ellese",
        "db",
        "docs/pavilion-ellese",
        "docs/projectFiles/エリーゼの館"
      ]
    },
    "tax_ledger": {
      "scopeRoots": [
        "apps/tax-ledger"
      ]
    },
    "ai_consult_tools": {
      "scopeRoots": [
        "ai-consult-tools"
      ]
    }
  }
}
```

対象プロジェクト以外の状態や差分をbundleへ混入させない。

Git管理する例は`config/project_profiles.example.json`、ローカル実設定は`local/project_profiles.json`とする。

`scopeRoots`はRepoRoot相対・`/`区切り・末尾`/`なしとし、空文字、絶対パス、`.`、`..`、同一プロファイル内の重複を拒否する。

所属判定は、対象パスが`scopeRoot`と一致するか、`scopeRoot + "/"`で始まる場合に一致とする。

---

## 8. CLI

```text
python ai-consult-tools/consult.py start
python ai-consult-tools/consult.py review
python ai-consult-tools/consult.py inspect
python ai-consult-tools/consult.py find <query> [--profile <name>]
python ai-consult-tools/consult.py structure sync
python ai-consult-tools/consult.py structure check
```

### `start`

- 構造同期
- プロファイル読込
- 初回include bundle生成
- 対象プロジェクトの最新ツリーを同梱

### `review`

- 対象パス限定diff
- unstaged、staged、未追跡を区別
- stage前の未追跡ファイルも収録
- 構造変更を収録

### `inspect`

- 関数
- クラス
- Markdown見出し
- SQL定義
- ファイル内部の軽量構造

### `find`

```text
python ai-consult-tools/consult.py find <query>
python ai-consult-tools/consult.py find <query> --profile <name>
```

- ローカルJSON構造インデックスに記録されたファイルだけを検索
- 検索前に現在構造を走査し、JSONインデックスが最新か確認
- 未生成、古い、形式不正の場合は自動更新せず終了コード2
- 更新が必要な場合は`structure sync`を案内
- 読み取り専用であり、ファイルとディレクトリを変更しない
- 大文字小文字を区別しない
- `\`は`/`へ正規化し、先頭`./`と末尾`/`を除去
- 完全な相対パス一致を最優先
- 完全なファイル名一致を次に優先
- ファイル名部分一致を部分パス一致より優先
- 同順位は相対パスの決定的ソート
- 複数候補はすべて表示し、勝手に1件へ決定しない
- `--profile`指定時は対象プロジェクト内だけに絞り込む
- ローカル`project_profiles.json`があれば優先し、なければexampleを使用
- 一致ありは終了コード0、一致なしは終了コード1、処理エラーは終了コード2

### `structure sync`

- ローカルインデックス生成先をRepoRoot内として安全確認
- 現在構造を1回走査
- 同一snapshotから`folder_tree.txt`とローカルJSONインデックスを生成
- 追加、削除、移動候補を表示
- 各ファイルを変更時だけ原子的に更新
- どちらかを更新した場合は`updated`、両方最新なら`current`

### `structure check`

- 現在構造と`folder_tree.txt`・ローカルJSONインデックスを比較
- 両方最新なら終了コード0
- どちらかが未生成・古い・形式不正なら終了コード1
- 走査・読込エラーなら終了コード2
- ファイルとディレクトリは変更しない

モデル別出力は以下で切り替える。

```text
--target chatgpt
--target claude
```

---

## 9. bundleの共通出力

スレッド開始用bundleには以下を生成する。

```text
REPO_OVERVIEW.md
PROJECT_TREE.md
STRUCTURE_STATUS.md
PATH_INDEX.md
SKIPPED.md
MANIFEST.csv
```

| ファイル | 役割 |
|---|---|
| `REPO_OVERVIEW.md` | 主要ルートとプロジェクト配置 |
| `PROJECT_TREE.md` | 対象プロジェクトの最新パスツリー |
| `STRUCTURE_STATUS.md` | 正本との差分 |
| `PATH_INDEX.md` | 要求パスと解決結果 |
| `SKIPPED.md` | 省略、除外、失敗理由 |
| `MANIFEST.csv` | 収録ファイルの機械可読一覧 |

モノレポ全体の巨大な`folder_tree.txt`は通常bundleへ同梱しない。

---

## 10. v4のファイル構成

```text
ai-consult-tools/
├─ README.md
├─ LICENSE
├─ consult.py
├─ src/
│  └─ ai_consult/
│     ├─ __init__.py
│     ├─ cli.py
│     ├─ config.py
│     ├─ inventory.py
│     ├─ search.py
│     ├─ filters.py
│     ├─ path_resolver.py
│     ├─ git_diff.py
│     ├─ bundle.py
│     └─ renderers/
│        ├─ __init__.py
│        ├─ chatgpt.py
│        └─ claude.py
├─ config/
│  ├─ consult.config.example.json
│  └─ project_profiles.example.json
├─ templates/
│  └─ session_start.md
├─ shared/
│  ├─ 00_ai_consult_operation_rules.md
│  ├─ consult.local.example.md
│  └─ SECURITY.md
├─ tests/
│  ├─ test_config.py
│  ├─ test_inventory.py
│  ├─ test_search.py
│  ├─ test_filters.py
│  ├─ test_path_resolver.py
│  ├─ test_git_diff.py
│  ├─ test_bundle.py
│  └─ test_renderers.py
└─ local/
   ├─ consult.config.json
   ├─ project_profiles.json
   ├─ consult.local.md
   └─ cache/
      └─ repo_structure_index.json
```

`local/`はGit管理しない。

新しいファイルは各フェーズで必要になった時点で追加し、最初から一括作成しない。

---

## 11. 現行ファイルの移行分類

### 維持・更新

- `ai-consult-tools/.gitignore`
- `ai-consult-tools/LICENSE`
- `ai-consult-tools/README.md`
- `ai-consult-tools/docs/00_v4_design_outline.md`
- `ai-consult-tools/shared/00_ai_consult_operation_rules.md`
- `ai-consult-tools/shared/SECURITY.md`
- `ai-consult-tools/shared/consult.local.example.md`
- `folder_tree.txt`

### 共通ファイルへ統合後に削除

- ChatGPT・Claude別の仕様書
- ChatGPT・Claude別のテンプレート
- ChatGPT・Claude別のセッションガイド
- release README
- モデル別example設定

### 一時的な互換ラッパー

- `chatgpt/consult_bundle_chatgpt.py`
- `claude/consult_bundle_claude.py`

V4-4までは既存実装を維持する。

V4-6で共通CLIを呼び出す薄いラッパーへ置換する。

### V4-6で削除

- `tree.txt`
- `duplicate_filenames_report.md`

### Git変更対象外

- `archive/`
- ChatGPT・Claudeの生成済みbundle
- `local/`の実設定
- RepoRootの`ai-consult-tools.zip`

---

## 12. 実装フェーズ

### V4-0 現状固定：完了

- ライブrepoの状態を確認
- 構造ファイルと参照元を確認
- Git変更を確認
- 現行ファイルを分類
- v4の追加・変更・削除対象を確定
- 実装順序を確定

### V4-1 共通コアと安全性

- 共通CLIの最小構成
- 共通設定読込
- RepoRoot境界
- symlink・junction escape拒否
- パス正規化
- 除外判定
- テキスト・バイナリ判定
- 文字コード判定
- 自動テスト基盤

### V4-2 構造インベントリ

- V4-2A：構造走査コア・`folder_tree.txt`形式確定（完了）
- V4-2B：`structure sync`・`structure check`（完了）
- V4-2C前半：JSONインデックス・プロジェクトプロファイル（完了）
- V4-2C後半：`find`（完了）

### V4-3 bundle生成

- V4-3A：共通bundle内部モデル（完了）
- V4-3B：Git差分収集（完了）
- V4-3C：review bundle共通組立（完了）
- V4-3D：start bundle共通組立（完了）
  - V4-3D-1：構造表示コア
  - V4-3D-2：startファイル収集
  - V4-3D-3：生成文書
  - V4-3D-4：`BundleModel(command=start)`への統合
  - V4-3D-5：統合・境界試験
- 構造走査は1回だけ実行し、`folder_tree.txt`とJSON構造インデックスを同一snapshotから同期する
- 生成5文書を固定順で配置し、その後ろに収録ファイル本文を配置する
- manifestは`BundleItem`から派生する
- 明示includeだけprofile外を許可し、profile外の構造情報は生成文書へ出さない
- V4-3D-5完了時の全試験：174件成功、3件skip（Windowsのsymlink作成権限による既存試験）
- V4-3D-5では実装欠陥は確認されず、試験追加だけを行った
- モデル別物理出力とCLI接続はV4-4で扱う

### V4-4 出力アダプター：完了

- V4-4A：共通レンダリング基盤
- V4-4B：ChatGPT向け決定的ZIP出力
- V4-4C：Claude向け結合Markdown・part分割
- V4-4D：共通CLIからの`start` / `review`接続
- V4-4E：統合・境界試験
- `BundleModel`は変更せず、物理出力設定を別の出力コンテキストとして扱う
- 共通CLIの成果物名は`<DocSet>_start[_<CaseName>]`、`<DocSet>_review[_<CaseName>]`とする
- 共通設定にChatGPT・Claude別の出力先とpart上限を追加する
- manifestは共通8列を使用し、生成文書名はV4共通モデルへ統一する
- BundleItem本文はorigin、git change、previous path、encoding、source metadataを保持する
- 生成テキストはUTF-8 BOMなし・LF・末尾LFありとする
- ChatGPT ZIPはentry順・timestamp・permissionを固定し、同一入力から同一バイト列を生成する
- Claude出力は実part名をINDEXへ記録し、未置換プレースホルダーを残さない
- 最終成果物は一時出力の完成・検証後に確定し、同名成果物は上書きしない
- 変更ゼロのreviewはCLIでは成果物を作らず、skipのみの場合は成果物を生成する
- 既存ChatGPT版・Claude版スクリプトは変更せず、V4-6で互換ラッパー化する
- V4-4完了時の全試験：196件成功、3件skip（Windowsのsymlink作成権限による既存試験）

### V4-5 運用文書整理

- 共通ルール短縮
- 正本の種類を分離
- 現行仕様と履歴を分離
- 文書新規作成規則
- 保留項目規則
- L1からL3の変更レベル
- TODO・引き継ぎ文の肥大化防止

### V4-6 移行・整理

- 旧スクリプトを互換ラッパー化
- 重複仕様・ガイドを統合
- `tree.txt`削除
- `duplicate_filenames_report.md`削除
- 旧生成物を通常配布対象から除外
- clean export
- 正式バージョン確定

---

## 13. リスク区分

| 作業 | 区分 |
|---|---|
| 既存処理へ影響しない共通コア追加 | L1 |
| `folder_tree.txt`の全面再生成 | L2 |
| 新CLIを実運用へ接続 | L2 |
| 旧スクリプトを互換ラッパーへ変更 | L3 |
| 旧仕様書や重複構造ファイルの削除 | L3 |

---

## 14. 完了条件

- ChatGPTとClaudeが同じ収集結果を使用する
- モデル差が最終出力形式だけになる
- RepoRoot外の内容を収録できない
- symlinkやjunction経由でも境界外へ出られない
- バイナリを本文として収録しない
- 対応文字コードを破損せず読み込める
- 明示includeの不足や除外を黙って省略しない
- 未追跡ファイルをstage前にレビューできる
- diff対象パスを限定できる
- 対象外プロジェクトの差分が混ざらない
- ファイルパス確認に通常mapが不要になる
- 初回bundleに最新の`PROJECT_TREE.md`が入る
- 構造変更後に`folder_tree.txt`が更新される
- 古い構造正本のままコミットへ進めない
- 仕様、設計、実装・実DB、進捗・保留を区別できる
- 用途不明な機能を根拠なく追加しない
- 現在地と次の作業を少数の文書で確認できる
