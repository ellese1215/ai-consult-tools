# 00 AI相談運用ルール

> File: 00_ai_consult_operation_rules.md
> Updated: 2026-06-07
> DocSet: 202606070000
> Version: 3.1.1
> Note: v3.1.1 はClaude版・ChatGPT版共通。AI固有の差異は各節内に【Claude】【ChatGPT】ラベルで明示する。

---

## このドキュメントの読み方

このドキュメントはClaude・ChatGPT共通の運用ルールを定義する。
AI固有の記述には以下のラベルを付ける。ラベルのない記述は両AIに共通で適用する。

- **【Claude】**：Claudeにのみ適用する
- **【ChatGPT】**：ChatGPTにのみ適用する

---

## 0. この文書の位置づけ

- 本書（00）は **AI相談の運用ルール**（推測禁止、参照確定、進め方、回帰防止）を定義する。
- スクリプトの技術仕様（引数・出力・フォーマット・除外規則）：
  - **【Claude】** `claude/01_make_consult_bundle_spec.md` を参照。
  - **【ChatGPT】** `chatgpt/01_make_consult_bundle_spec_chatgpt.md` を参照。
- セッション開始手順・モード選択の判断基準：
  - **【Claude】** `claude/03_claude_session_guide.md` を参照。
  - **【ChatGPT】** `chatgpt/03_chatgpt_session_guide.md` を参照。

---

## 1. スレッド開始時の必須手順

新スレッド開始時、AIは以下の順で**宣言してから**作業を開始する。宣言なしの着手は禁止。

1. **運用ルール認識**：本ドキュメントを読んだことを宣言する
2. **TODOドキュメント確認**：添付された `docs/todo/` 配下のTODOドキュメントを読み、現在のPhase・作業を確認・宣言する
3. **引き継ぎ情報確認**：前スレッドの引き継ぎがある場合は残課題・次の相談内容を把握したことを宣言する
4. **`consult.local.md` の参照**（参照束に含まれる場合）：以下を把握してから着手する
   - **ビルドコマンド**：TypeScript / SCSS 変更後のビルドコマンド。記載がない場合はBQで停止する
   - **includeコマンドパターン**：よく使うinclude bundle生成コマンド
   - **その他の注意事項**：プロジェクト固有の運用注意事項

---

## 2. Blocking Questions（BQ）ルール

作業中に不明点・確認事項が生じた場合は**作業を止めて**BQとして提示する。

- `BQ1`、`BQ2` のように番号を付けて列挙する
- BQへの回答が得られるまで、該当部分の実装・提案を行わない
- BQは「作業を止める必要がある質問」に限定する。軽微な確認は作業中に随時行う
- BQには次の3点を記載する：①質問内容　②質問が必要な理由（影響範囲）　③回答がない場合のリスク

---

## 3. 禁止事項

### 3.1 推測の禁止（最重要）

仕様・コード・データ構造について**推測で補完しない**。根拠が確認できるまで実装案・修正案を提示しない。

- 不明点は必ず作業を停止し、BQで質問する
- 根拠となるファイルが必要な場合はユーザーに提示を依頼する
- 「おそらく〇〇」「一般的には〇〇」のような補完は禁止
- 参照束に含まれていない実装値（SCSSのmixin定義値・変数値・TypeScriptの定数・PHPの設定値など）を記憶や推測で答えない → 該当ファイルを含むinclude bundleの生成コマンドを提示してユーザーに要求する
- AIがincludeを必要と判断した場合は、ユーザーより先に率先してincludeを要求する
- includeするファイルのパスが不明な場合、パスを推測してinclude生成コマンドを提示しない。先にmapモードでbundleを要求し、所在を明らかにしてからincludeを要求する

### 3.2 コード・仕様の根拠ルール

- **コード（実装）を一次根拠**とし、コメント・ドキュメント記述・ログ文言は二次根拠とする
- コードとコメントが矛盾する場合は、コメントの訂正案を必ず提示する（ただし挙動変更は「仕様案→合意→ドキュメント→コード」の順を守る）
- **【Claude】** `--xxx`（スクリプト引数）は `consult_bundle_claude.py` の `argparse` 定義に存在するものだけ記載する
- **【ChatGPT】** `--xxx`（スクリプト引数）は `consult_bundle_chatgpt.py` の `argparse` 定義に存在するものだけ記載する
- `--xxx`（Gitオプション）は `DIFF_INDEX.md` の `DiffArgs` に実際に含まれるものだけ記載する。出典を示せない `--xxx` は記載禁止

### 3.3 DB作業時の根拠ルール

- DB seed / migration / repository SQL 作成・修正時は、過去DDL・古いschemaファイル・過去docs・AI記憶を第一根拠にしない
- 最新の実DB構造は `db/current/` 配下のスナップショットを第一参照とする
- `db/current/` と migration / schema / docs が矛盾する場合は `db/current/` を優先し、差異を docs / TODO に記録する
- DB構造変更を伴うmigration / seed 適用後は、`db/current/schema_inventory.sql` を実行し、`db/current/schema_inventory_result.md` と必要なtable summaryを更新する
- `db/current/` が未整備・古い・実行エラーと矛盾する場合は、対象テーブルの `information_schema` 診断SQLを `db/diagnostics/` 配下に `.sql` ファイルとして保存し、ユーザー実行結果を確認してから修正する

### 3.4 破壊的変更の禁止

修正提案は回帰（既存成果物の欠落）を禁止し、破壊的変更は事前明示と承認を必須とする。

### 3.5 一次根拠の文字列改変禁止

include bundleなどで渡された一次根拠に含まれる文字列（見出し・アンカー・セレクタ・変数名・関数名・シンボル）を、AIが言い換え・要約・推測変換して使うことを禁止する。

- 検索文字列・置換アンカーは一次根拠から**機械的にコピー**して使う
- 「それらしい」アンカーをAIが生成することは禁止。実在を確認できない文字列は使わない
- 一次根拠と完全一致しない文字列を使う場合は必ずBQで確認する
- include bundleで渡された内容を要約・言い換え・記憶ベースで扱うことを禁止する。根拠を参照する場合はbundle内の該当箇所を直接引用して根拠とする

---

## 4. 参照確定（作業開始条件）

AIは作業開始前に「唯一の正（参照束）」を明言し、DocSetを引用して一致確認を完了するまで仕様案・修正案・コード案を提示しない。

### 4.1 4モード運用（map → include → diff / repo）

| モード | 用途 |
|--------|------|
| **map** | repoと同じ収集範囲から本文なしの軽量地図を作る。include候補を広めに拾うための索引 |
| **include** | 必要な本文を過不足なく抽出。仕様確定・具体修正の一次根拠 |
| **diff** | 修正後の差分をGit事実と整合する形で固定。過不足・副作用の根拠付き確認 |
| **repo** | mapでは不足する場合に限り使用。本文付きの全体横断スナップショット |

**原則フロー：**
要求 → map（include候補の洗い出し）→ include（本文根拠の固定）→ 仕様案 → 合意 → diff（レビュー）→ 試験

- mapは本文根拠ではないため、map束だけを根拠に具体的なコード差分・仕様差分を作らない
- 実装後の確認はdiffを基本とする
- **各モードの確認はすべてスクリプトの生成物で行う。ターミナル上のdiffコマンドによる直接確認は行わない**

### 4.2 参照束の形式と唯一の正

参照束の形式はAIによって異なる。

**【Claude】** 参照束の成果物は **MDファイル（`<DocSet>_<Mode>[_<CaseName>].md`）を唯一の正**とする。大きい場合は `_part1.md` / `_part2.md` に分割される。分割時はすべてのpartを合わせて唯一の正とする。

**【ChatGPT】** 参照束の成果物は **ZIPファイル（`<DocSet>_<Mode>[_<CaseName>].zip`）を唯一の正**とする。ZIP内に INDEX.md / TREE.md / MANIFEST.csv / partファイル群が含まれる。

**共通ルール：**
- 各カテゴリで「唯一の正」は常に1つ。同カテゴリで新しい生成物が提示された場合、古いものは無効（参照禁止）
- 参照優先順位（衝突時）：**Diff > Include > Repo > Map**

### 4.3 参照束の最低要件

参照束には最低限、INDEX（目的・唯一の正・DocSet・含有物の概要）、TREE（フォルダ構造）、MANIFEST（ファイル一覧）を含める（スクリプトが自動生成）。

### 4.4 基盤メンテナンス例外（INDEX.mdが存在しない相談）

次の条件をすべて満たす場合に限り、INDEX.mdを用いた参照確定を例外扱いとしてよい。

- 相談内容が「相談基盤そのものの改修」である
  - **【Claude】** 対象例：`ai-consult-tools/consult_bundle_claude.py` またはその仕様書
  - **【ChatGPT】** 対象例：`ai-consult-tools/consult_bundle_chatgpt.py` またはその仕様書
- map/repo/include/diffの参照束（生成物）を前提にしていない

この例外時は、ユーザーが提示した**基盤メンテファイル群を「唯一の正」**とし、以下を引用して「参照確定完了（基盤メンテ例外）」を宣言する。

- `00_ai_consult_operation_rules.md` の DocSet/Version
- 対象スクリプトのヘッダー（DocSet/Version等）
- 対象仕様書の DocSet/Version（仕様変更を伴う場合は必須）

**最低同梱物（欠けていたら停止）：**
- `00_ai_consult_operation_rules.md`
- 対象スクリプト（例：`consult_bundle_claude.py` / `consult_bundle_chatgpt.py`）
- 対象仕様書（例：`01_make_consult_bundle_spec.md`）（仕様変更を伴う場合）

---

## 5. 基本フロー

```
要求 → 仕様案 → 合意 → ドキュメント → コード → 試験
```

### 5.1 仕様案の提示

- 不明点は必ず質問（BQとして提示）
- 推測禁止
- 仕様案には必ず根拠を明示する（既存仕様書・コードなど）
- 仕様案には必ず「受入条件（AC）」を含める（最低3点：正常系/異常系/境界）

### 5.2 仕様の合意

ユーザーが「OK」「それで進めてください」などの承認をもって仕様確定。

### 5.3 影響範囲の横断チェック

以下のレイヤーを横断的に確認する：API / DB・モデル / UI・UX / 多言語 / 権限 / SEO / ログ / 移行 / バリデーション / エラーハンドリング / プロジェクト固有仕様

AIは影響範囲チェックの結果として次を提示する：
- 影響が想定される領域
- 影響がありそうなファイル群（パス付き）
- 「確認が必要だが参照束に含まれていないファイル」の追加要求リスト → BQに統合
- include参照束としてまとめるべき最小セット案

---

## 6. ドキュメントフェーズ（仕様合意後）

1. AIが修正案を**コピー＆ペースト可能なMarkdown**で提示（DocSetのバージョン更新案も含める）
2. ユーザーがローカルで修正を反映し、ドキュメントヘッダーの**DocSetバージョンを更新**
3. AIが最新DocSetを基準に整合性を確認 → 問題なければ「仕様書確定」

---

## 7. コードフェーズ（仕様書確定後にのみ実施）

### 7.1 コード修正案の提示ルール

- 仕様書に完全準拠・推測禁止
- 原則としてinclude参照束を根拠にコード修正案を作成する
- コードを提示する場合は必ず「ファイルパス」を併記する
- 原則として「全文」を提示する（ユーザーがdiff指定した場合のみdiff）
- **ファイルの書き換え・新規作成は、コードブロックではなく `.py` スクリプトファイルとして提示する（7.3節参照）**
  - コードブロックは、実行コマンド例・参照用コード断片・AI内容確認用にとどめる
  - 「コードブロックで全文提示した」だけではスクリプト提示の義務を果たしたことにならない

### 7.2 patchの運用

ファイルの書き換え・新規作成は **`.py` スクリプトを原則**とする（7.3節参照）。patchは `.py` で対応できない例外的なケースにのみ使用する。

**patchを使う場合（例外時）の必須ルール：**
- **fresh include bundle** または **fresh diff bundle** に含まれる実ファイル内容を根拠にする
- patchは変更前後のファイルから作った**機械的diff**に限定する。失敗した場合は即興修正版を出さず原因を確認する
- 提示前に必ず先出しで示す：対象ファイル / 実在見出し・シンボル・selector / 変更箇所と根拠 / 不明点がないこと（またはBQ）
- **【ChatGPT】** patch適用時は `git apply --check` を先に実行し、成功した場合だけ `git apply` する
- patch適用後は原則としてstaged diff bundleを生成して査読する

**patch失敗時の根拠管理：**
- 失敗したpatchは破棄扱い。同じ抽出表示・チャット上の断片を根拠にv2/v3 patchを繰り返し生成しない
- 再生成する場合の根拠は次のいずれか：fresh include bundle、fresh diff bundle、ユーザーのローカル実体確認結果、`git hash-object`、行番号付き本文、実ファイルから機械的に作成されたdiff、raw添付された対象ファイル
- 以下はpatch生成根拠として使わない：truncated snapshot、部分抽出表示、チャット上の部分引用、途中で切れたMarkdown snapshot、失敗したpatchの目視補修結果、AIの記憶や推測
- 複数ファイルpatchで一部だけ確認した場合、確認済みと未確認ファイルを同じpatchに混在させない

**コードブロックを出す場合：**
- 開始フェンスと終了フェンスが対応していることを確認する
- コマンド例は原則として1行で提示する

### 7.3 Pythonスクリプト（`.py`）の配置ルール

既存ファイルの書き換え・新規作成が必要な場合は、**Pythonスクリプト（`.py`）を原則**とする。

**`.py` スクリプトの必須要件（共通）：**
- **配置場所：RepoRoot直下（`<your-repo>/`）**
- `.py` には以下を含める：
  - 対象ファイルの存在確認
  - 重複防止（2回目実行時に二重適用しない）
  - **検索文字列はinclude bundleから機械的にコピーし、AIが変形しない**
  - **アンカー検出件数を実行時に出力し、0件なら `sys.exit(1)` で停止する**
  - **dry-run（置換前の一致確認）を先に実行し、ユーザーが目視確認してから本実行する**
  - UTF-8 BOMなし保存
- **スクリプトが50行を超える場合は必ずダウンロード可能な `.py` ファイルとして提示する。チャット内コードブロックへの全文貼り付けで代替しない**
- 一時 `.py` はcommit対象にしない。diff bundle確認後に削除し、`git status --short --untracked-files=all` で残存確認する

**実行コマンドの形式：**
- **【Claude】** `cd <your-repo>; python <ファイル名>.py`
- **【ChatGPT】** `cd <your-repo>; python <ファイル名>.py`

**【ChatGPT】`.py` 提示前の事前検証（必須）：**
- `py_compile` による構文チェック
- include bundle または diff bundle から復元した対象ファイルコピーへのドライラン適用
- アンカー一致件数確認・2回目実行時の重複防止確認・変更対象ファイル一覧確認
- 上記の検証結果を提示文に明記する。検証できない項目がある場合は「何を検証できていないか」を明示し、必要ならBQで停止する
- `.py` を生成しただけで構文チェック・コピー適用テストを行わないまま「検証済み」と表現してはならない

**スクリプトを使う操作（ファイル本文編集には使わない）：**
- **【Claude】** `consult_bundle_claude.py` による map / include / diff / repo bundle生成
- **【ChatGPT】** `consult_bundle_chatgpt.py` による map / include / diff / repo bundle生成
- `git` コマンド操作（add / commit / push / status 等）
- 一時ファイルの削除

特に日本語・長文ドキュメント・コードフェンスを含む文書・CRLF/LF差異の影響を受けやすいファイルでは `.py` を優先する。

### 7.4 SQLの実行ルール

- DB seed / migration / diagnostics SQLの作成・修正・確認まではAIが支援してよい
- DBへの反映はユーザーがphpMyAdmin・ターミナル・ローカル手順により**手動実行**する
- DB名・接続方法・実行権限が参照束またはユーザー明示で確認できない状態で、SQL直接実行コマンドを提示しない
- AIが出力するSQLは `.sql` ファイルとして提示する（`db/seeds/`・`db/migrations/`・`db/diagnostics/` 配下を原則とする）
- AIがSQLを案内する場合は、実行コマンドではなく対象 `.sql` ファイルのパス・実行目的・反映後に確認すべき結果を優先して案内する

---

## 8. スクリプト適用後の標準手順

Pythonスクリプト適用が成功したら以下の順で進める。

**ステップ1：変更種別チェック**

```bash
# PHPファイルを変更した場合
php -l <変更したPHPファイルのパス>
# 「No syntax errors detected」が出れば成功

# TypeScript / SCSS を変更した場合
# → consult.local.md の「ビルドコマンド」セクションを参照。記載がない場合はBQで停止する

# Markdownのみを変更した場合
git diff --check
```

**ステップ2：diff bundleを生成してAIに添付**

【Claude】
```bash
cd <your-repo>; python ai-consult-tools/claude/consult_bundle_claude.py --mode diff --repo-root <your-repo> --case-name "<相談名>"
```
生成された `.md` ファイルをAIに添付する。

【ChatGPT】
```bash
cd <your-repo>; python ai-consult-tools/chatgpt/consult_bundle_chatgpt.py --mode diff --repo-root <your-repo> --case-name "<相談名>"
```
生成された ZIP をAIに添付する。

AIは変更内容・漏れ・副作用を確認する。

**ステップ3：Pythonスクリプトを削除して残存確認**（チェック・diff bundle確認が通った後に提示）

【Claude / ChatGPT 共通】
```bash
# Linux / Mac
rm <スクリプト名>.py && git status --short --untracked-files=all
```

```powershell
# Windows
Remove-Item <your-repo>\<スクリプト名>.py -ErrorAction SilentlyContinue; git status --short --untracked-files=all
```

**ステップ4：問題なければ9章のGit確定ルーティンへ進む**

---

## 9. Git確定ルーティン

コード・ドキュメントの修正を反映した後は、原則としてcommitで止めず、pushまでを通常完了条件とする。ただし、別件の未追跡ファイル・一時patch・consult_case生成物を巻き込まない。

```bash
# 1. 対象ファイル限定で状態確認
git status --short -- <path1> <path2> ...

# 2. 変更種別チェック（8章ステップ1を参照）

# 3. 対象ファイルだけをstagedにする
git add <path1> <path2> ...

# 4. staged差分の基本エラーを確認
git diff --check --cached -- <path1> <path2> ...
# 出力がなければ問題なし

# 5. diff bundleを生成してAIに添付（8章ステップ2を参照）

# 6. 問題がなければcommit
git commit -m "<type>(<scope>): <summary>"

# 7. 状態確認
git status --short -- <path>
git log --oneline -3

# 8. push（monorepo全体）
git push origin master

# 9. push後にHEADとorigin/masterの一致を確認
git log --oneline -3
# HEAD -> master, origin/master, origin/HEAD が同じコミットを指していれば完了
```

**注意：**
- `git add .`・`git add -A`・対象外ファイルを含む一括addは原則禁止
- consult_case配下（`ai-consult-tools/consult_case/`）はユーザーが明示しない限り削除しない
- push前に別件差分や未追跡ファイルが見えても、今回対象でないものは勝手に整理・削除・stageしない
- commit / pushを行わずに終了する場合は、その理由と未完了の次手順を明記する

---

## 10. 動作試験フェーズ

### 10.1 AIが試験項目・チェックリストを作成

仕様に応じて以下の観点で作成する：正常系 / 異常系 / 境界値 / 権限 / 多言語 / SEO / ログ / 移行 / UI・UX / APIレスポンス / DB反映

### 10.2 ユーザーがローカルで試験を実施

- 結果をAIに報告する
- 試験で重大な不具合が出た場合は、原則として直前コミットへ戻してから修正方針を再検討する

---

## 11. DocSet運用ルール

- すべての仕様書・コード提案は**DocSetバージョン**を基準に判断する
- ユーザーがドキュメントを更新するたびにDocSetを更新する
- DocSetの更新がない状態でコード修正に進むことは禁止
- DocSetは仕様・コード・生成物の根拠バージョンであり、必ず一致させる

---

## 12. スレッド終了時の必須手順（TODO連携）

スレッド内で対応した実装・方針決定・調査結果は、引き継ぎ文を作成する前に、必ず該当TODOドキュメントへ追記・修正する。

**手順（この順序を守る）：**
1. スレッド内の作業内容を整理し、該当Phaseの進捗・実装記録・残課題を明確にする
2. TODOドキュメントの該当箇所を更新するスクリプトを作成・実行する
3. 更新内容をcommit・pushする
4. 引き継ぎ文を作成する

TODOドキュメントの更新なしに引き継ぎ文を作成しない。

### 12.1 引き継ぎ文の構成ルール

引き継ぎ文は以下の**ブロック構成・出力順を必ず守る**。混在・順序変更は禁止。

**【ブロック1】次スレッドへのinclude生成コマンド（コードブロック単独で先出し）**

【Claude】
```bash
cd <your-repo>; python ai-consult-tools/claude/consult_bundle_claude.py --mode include --repo-root <your-repo> --case-name "<相談名>" --include-paths "ai-consult-tools/shared/00_ai_consult_operation_rules.md" "ai-consult-tools/local/claude/consult.local.md" "<TODOドキュメントのパス>" "<現在作業に必要な実ファイル>"
```

【ChatGPT】
```bash
cd <your-repo>; python ai-consult-tools/chatgpt/consult_bundle_chatgpt.py --mode include --repo-root <your-repo> --case-name "<相談名>" --include-paths "ai-consult-tools/shared/00_ai_consult_operation_rules.md" "ai-consult-tools/local/chatgpt/consult.local_chatgpt.md" "<TODOドキュメントのパス>" "<現在作業に必要な実ファイル>"
```

include生成コマンドは引き継ぎ本文と混在させない。コマンド単体のコードブロックとして単独で先に出すこと。

**【ブロック2】引き継ぎ本文（以下の順で記載）**

冒頭に次の文を通常本文として書く：
「上のinclude bundle生成コマンドを実行し、生成された【Claude】`.md` ファイル / 【ChatGPT】ZIPファイルを添付します。添付後、この相談を開始してください。」

続けて以下の内容を含める（この順で記載）：
1. **次スレッドの目的**（何をするか）← 必須・先頭に書く
2. **再開点**（どこから始めるか）← 必須
3. 完了済み作業の記録
4. 残課題・注意事項
5. 失敗内容・経緯（あれば末尾に）

ブロック1とブロック2を混在させない。「失敗内容のみ」を書いて目的・再開点を省くことは禁止。

**引き継ぎ文に含める新スレッドへの指示（共通）：**
- 添付の参照束を唯一の正として参照確定する
- `00_ai_consult_operation_rules.md` を最優先で読み、要点を引用して「運用ルール認識完了」を宣言してから着手する
- `consult.local.md` も確認し、ビルドコマンドやinclude/diffコマンドパターンを推測しない
- TODOドキュメントを読み、現在どのPhaseの相談かを確認・宣言する
- すぐにpatch / diffを出さず、まず以下を提示する：実在ファイル一覧 / 実在見出し・セレクタ / 現在のPhase上の位置 / 次に変更・確認する予定箇所 / その根拠 / BQ

---

## 13. 補助ルール

### 13.1 AIの役割

仕様の整理・横断観点の抜け漏れチェック・文書化・差分レビュー（diff）を担う。仕様・判断・合意の中核をAIが行い、推測を排除する。最終的な仕様根拠は常に参照束（DocSet一致）で担保する。

### 13.2 個人名の非使用

このチャット内および関連するすべてのドキュメント・提案において、ユーザーの個人名を記載しない。呼称が必要な場合は「あなた」「開発者」「ご相談者」など、個人を特定しない表現を使用する。

### 13.3 診断出力（--diag）の扱い

**【Claude】** `--diag` はスクリプトの診断出力（コンソール出力）を有効化するフラグであり、**既定では無効**。トラブルシュート時のみ使用し、通常の相談フローでは使わない。

**【ChatGPT】** `--diag` は同様の目的のフラグ。

### 13.4 公開リポジトリ運用ルール

このプロジェクトはmonorepo構成をとる。リモートは2つあり、役割が異なる。

| リモート名 | 対象 |
|------------|------|
| `origin` | monorepo全体（非公開） |
| `public` | `ai-consult-tools/` 配下のみ（公開） |

- `git push origin master` はmonorepo全体のpush。通常のコード反映はこれを使う
- `public` へのpushは `ai-consult-tools/` 配下を公開する操作であり、monorepo全体のpushとは別操作として扱う
- `ai-consult-tools/` 配下以外のファイルを `public` リモートに含めない
- `public` への反映が必要な場合は、操作前に対象リモート・対象パス・subtreeコマンドをBQで確認してから実行する
- remote名・URL・push対象は推測しない。`consult.local.md` に記録がない、またはinclude bundleに含まれていない場合はBQで停止する

---

## 14. このルールの目的

- 仕様と実装のズレをゼロにする
- 推測による誤実装を防ぐ
- DocSetによるバージョン管理で混乱を防ぐ
- 長期開発でも整合性を保つ

---

## 15. 今後の改訂について

- 本ドキュメントはプロジェクトの最上位に位置する
- 必要に応じてDocSetバージョンを更新しながら改訂する
- 改訂は必ず「仕様 → 合意 → ドキュメント → コード → 試験」の流れに従う
