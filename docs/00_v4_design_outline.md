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
python ai-consult-tools/consult.py find <query> [--profile <name>]
python ai-consult-tools/consult.py structure sync
python ai-consult-tools/consult.py structure check
python ai-consult-tools/consult.py start --target <chatgpt|claude> --profile <name>
python ai-consult-tools/consult.py review --target <chatgpt|claude> --profile <name>
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
├─ docs/
│  ├─ 00_v4_design_outline.md
│  └─ 01_current_spec.md
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

## 11. 文書と現行ファイルの移行分類

### 11.1 V4-5で確定した正本の種類

| 種類 | 正本 | 役割 |
|---|---|---|
| 公開入口 | `README.md` | 目的、導入、基本コマンド、文書案内 |
| 共通運用ルール | `shared/00_ai_consult_operation_rules.md` | 相談、合意、変更、確認、Git安全運用 |
| 現行技術仕様 | `docs/01_current_spec.md` | 共通CLI、設定、bundle、出力契約 |
| セキュリティ | `shared/SECURITY.md` | 除外、機密情報、生成物の取扱い |
| 公開設定例 | `config/*.example.json` | 共通設定とプロジェクトプロファイルの例 |
| V4移行計画・履歴 | `docs/00_v4_design_outline.md` | 移行理由、フェーズ境界、完了記録 |
| ローカル環境情報 | `local/consult.local.md` | RepoRoot、ビルド、実行、remoteなどの固有情報 |
| 現行動作の検証根拠 | `src/ai_consult/`と`tests/` | 実装挙動と自動試験 |

現行仕様、移行履歴、ローカル固有情報、保留事項を同じ文書へ混在させない。

### 11.2 維持・更新

- `ai-consult-tools/.gitignore`
- `ai-consult-tools/LICENSE`
- `ai-consult-tools/README.md`
- `ai-consult-tools/docs/00_v4_design_outline.md`
- `ai-consult-tools/docs/01_current_spec.md`
- `ai-consult-tools/shared/00_ai_consult_operation_rules.md`
- `ai-consult-tools/shared/SECURITY.md`
- `ai-consult-tools/shared/consult.local.example.md`
- `ai-consult-tools/config/consult.config.example.json`
- `ai-consult-tools/config/project_profiles.example.json`
- `folder_tree.txt`

### 11.3 ローカル正本

```text
ai-consult-tools/local/
├─ consult.config.json
├─ project_profiles.json
├─ consult.local.md
└─ cache/
   └─ repo_structure_index.json
```

`project_profiles.json`はローカル上書きが必要な場合だけ作成する。存在しない場合は`config/project_profiles.example.json`を使用する。

### 11.4 V4-6まで保持する旧版資料

以下はV4共通CLIの現行仕様ではない。V4-5では旧版資料であることを明示するだけとし、最終統合と削除はV4-6で行う。

- ChatGPT・Claude別の仕様書
- ChatGPT・Claude別のテンプレート
- ChatGPT・Claude別のセッションガイド
- release README
- ChatGPT版の旧テストコマンド文書
- モデル別example設定
- `local/chatgpt/`と`local/claude/`の旧実設定

### 11.5 一時的な互換ラッパー

- `chatgpt/consult_bundle_chatgpt.py`
- `claude/consult_bundle_claude.py`

V4-6で共通CLIを呼び出す薄いラッパーへ置換する。V4-5では変更しない。

### 11.6 V4-6で削除

- `tree.txt`
- `duplicate_filenames_report.md`
- 統合後に不要となる旧モデル別文書・設定例

### 11.7 Git変更対象外

- `archive/`
- ChatGPT・Claudeの生成済みbundle
- `local/`の実設定
- RepoRootの`ai-consult-tools.zip`

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

### V4-5 運用文書整理：完了

- 文書の実在状況と役割を確認
- 公開入口、共通運用、現行技術仕様、移行履歴、ローカル情報を分離
- `docs/01_current_spec.md`を現行技術仕様の正本として新規作成
- 共通ルールを短縮し、技術仕様とローカル情報を分離
- 現行仕様と履歴を分離
- 文書新規作成規則
- 保留項目規則
- L1からL3の変更レベル
- TODO・引き継ぎ文の肥大化防止
- `README.md`、`SECURITY.md`、共通localテンプレート、共通設定例を現行共通CLIへ更新
- Git管理外の共通local設定とローカル環境文書を新設
- 旧モデル別9文書は削除せず、V4-6まで保持する旧版資料であることだけを明示
- `inspect`案は未採用としてV4対象から削除
- 共通設定例の新しいlocal参照先に合わせて設定試験の期待値を更新
- `folder_tree.txt`と構造キャッシュはV4-5のコミット対象外とし、旧スクリプトの互換ラッパー化と旧文書の最終統合・削除はV4-6へ残した
- V4-5完了時の全試験：196件成功、3件skip（Windowsのsymlink作成権限による既存試験）

### V4-6 移行・整理

#### V4-6A 契約確定：完了

- 旧ChatGPT版・Claude版スクリプトの実在内容と、現行共通CLIとの差分を確認した
- 旧スクリプトのファイルパスと`map`、`repo`、`include`、`diff`の4モード名は互換入口として維持する
- 互換入口では`--profile`を必須とし、ChatGPT版は`chatgpt`、Claude版は`claude`へtargetを固定する
- `map`は構造資料中心の`start`、`repo`は選択profileの`scopeRoots`全体を対象にした`start`、`include`は明示対象付き`start`、`diff`は現行`review`へ変換する
- staged限定、unstaged限定、任意ref間diff、旧basename検索、絶対パスinclude、旧出力形式、旧設定schemaの自動読替えは維持しない
- 未対応旧引数と旧設定schemaは成果物生成前に終了コード2で拒否し、現行入口への移行を案内する
- 旧ChatGPT設定例と現行共通local設定を比較し、現行共通設定例へ追加すべき有効設定はないことを確認した
- 旧モデル別文書・設定例は、互換ラッパー実装と代替先確認後に削除する
- `tree.txt`と`duplicate_filenames_report.md`は削除し、`folder_tree.txt`と`local/cache/repo_structure_index.json`は維持する
- 通常配布対象はpublicリポジトリの正式追跡ツリーとし、clean exportは同じツリーを`git archive`したZIPとする
- バージョン正本は`src/ai_consult/__init__.py`の`__version__`一か所とし、正式版は`4.0.0`とする
- release ZIP名は`ai-consult-tools-4.0.0.zip`、public tagは`v4.0.0`とし、CHANGELOGとGitHub Releaseは新設しない
- V4-6Aでは現行CLI動作、旧スクリプト、旧文書を変更しない

#### V4-6B 互換ラッパー：完了

- 共通の旧引数変換モジュール`src/ai_consult/legacy.py`を追加した
- ChatGPT版・Claude版旧スクリプトを、現行共通CLIだけを呼び出す薄い互換ラッパーへ置換した
- 固定target、`--profile`必須、4モード変換、旧設定schemaと未対応旧引数の拒否を実装した
- Claude旧入口の`--help`には非対応の`--include-set`を表示しない
- READMEと現行技術仕様へ互換入口の現行契約を反映した
- 互換入口専用試験13件を追加した
- V4-6B完了時の全試験：209件成功、3件skip（Windowsのsymlink作成権限による既存試験）

#### V4-6C 旧構成整理：公開整理完了

- 旧モデル別仕様書、README、ガイド、テンプレート、設定例11件を削除した
- Git管理外の`local/chatgpt/`と`local/claude/`を削除し、共通local構成へ統一した
- `tree.txt`と`duplicate_filenames_report.md`を削除した
- README、現行技術仕様、V4移行履歴、`.gitignore`を統合後の構成へ更新した
- Git管理対象の現行ファイルに、削除した旧文書・旧設定例への参照が残っていないことを確認した
- V4-6C公開整理後の全試験：209件成功、3件skip（Windowsのsymlink作成権限による既存試験）
- 構造正本とローカル構造インデックスの同期は、別案件の未追跡ファイルを混在させないため、V4-6Dの最終確認へ繰り越した

#### V4-6D 正式release：完了

- バージョン正本の`__version__`を`4.0.0`へ更新し、`consult.py --version`で確認した
- READMEの削除前文言を除去し、バージョン正本と配布方法を明記した
- active RepoRootで構造正本とローカル構造インデックスを同期し、1751件でcurrentを確認した
- `git archive`により`ai-consult-tools-4.0.0.zip`を生成した
- clean exportの41ファイルがpublic追跡ツリー41ファイルと完全一致することを確認した
- clean exportにlocal、cache、archive、consult_case、consult_project、`__pycache__`、秘密情報らしいファイル名、旧モデル別文書・設定例が含まれないことを確認した
- 作業ツリーとclean export展開後の双方で209件の試験が成功し、Windowsのsymlink作成権限による既存3件だけがskipとなった
- originへpushし、publicへsubtree pushし、publicへ`v4.0.0` tagを作成する正式公開手順を確定した
- V4共通CLIへの移行、旧構成整理、clean export、正式バージョン確定を完了した

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
