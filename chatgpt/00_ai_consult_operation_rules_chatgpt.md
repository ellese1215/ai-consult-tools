# 00 AI相談運用ルール

> File: 00_ai_consult_operation_rules.md
> Updated: 2026-06-06 20:30
> DocSet: 202606060310
> Version: 1.9.5
> Note: v1.9.5 では、既存ファイル改修時の第一候補を PowerShell `.ps1` から Python `.py` に改め、ChatGPT 側で構文チェックとドライラン検証を行ってから提示する運用を明確化する。

---

## 0. この文書の位置づけ（最初に読む）

- 本書（00）は **AI相談の運用ルール**（推測禁止、参照確定、進め方、回帰防止）を定義する。
- スクリプトの **技術仕様**（引数、出力、フォーマット、除外規則の詳細）は `01_make_consult_bundle_spec.md` を参照する。

### 0.1 スレッド開始時にChatGPTがすること（必須）

新スレッド開始時、ChatGPTは以下の順で宣言してから作業を開始する。

1. **運用ルール認識の宣言**：本ドキュメント（`00_ai_consult_operation_rules.md`）を読んだことを宣言する
2. **TODOドキュメント確認の宣言**：添付された `docs/todo/` 配下のTODOドキュメントを読み、現在どのPhaseのどの作業に相当する相談かを確認・宣言する
3. **引き継ぎ情報の確認**：前スレッドからの引き継ぎ情報がある場合は内容を確認し、残課題・次の相談内容を把握したことを宣言する
4. **作業開始**：上記3点の宣言が完了してから作業を開始する

宣言なしに作業を開始することは禁止する。

### 0.2 Blocking Questions（BQ）ルール

作業を進める上で不明点・確認事項がある場合は、作業を止めて **Blocking Questions（BQ）** としてユーザーに提示する。

- BQは `BQ1`、`BQ2` のように番号を付けて列挙する
- BQへの回答が得られるまで、該当部分の実装・提案を行わない
- 推測で進めることは禁止（1.1節参照）
- BQは「作業を止める必要がある質問」に限定し、軽微な確認は作業中に随時行う

### 0.3 4モード運用（map→include→diff / repo）

1) **map**：repo と同じ収集範囲から本文なしの軽量地図を作り、include束に入れる対象ファイル候補を広めに拾いやすくする
2) **include**：mapで洗い出した候補をもとに必要な本文を過不足なく抽出し、仕様検討・精査・具体修正の一次根拠にする
3) **diff**：修正後の差分を Git 事実と整合する形で固定し、過不足・副作用を根拠付きで確認する
4) **repo**：mapでは不足する場合に限り、本文付きの全体横断スナップショットとして使用する

（※ map/include/diff/repo のコマンド例や出力仕様は 01 を参照）

---

## 1. 禁止事項

### 1.1 推測の禁止

- 仕様・コード・データ構造について **推測で補完しない**
- 不明点がある場合は **必ず作業を停止し、質問する**
- 根拠となる仕様書・コード・ファイルが必要な場合は **ユーザーに提示を依頼する**
- 「おそらくこうだろう」という判断は禁止
- 根拠が確認できるまで実装案・修正案を提示しない

### 1.1.1 現仕様の判断は「コメント」ではなく「コード」を一次根拠とする（v1.4.6）

- 現在の仕様（実際の挙動）について回答する際は **コード（実装）を一次根拠**にする
- コメント（コード内コメント/ドキュメント記述/ログ文言）は **二次根拠**とし、コードより優先しない
- **コードとコメントが矛盾する場合**：
  - コメント（またはドキュメント）の **訂正案**を必ず提示する
  - ただし、挙動自体を変える提案は「仕様案→合意→ドキュメント→コード」の順を守る
- 目的：コメントの古さ・誤記に引きずられて誤判断するリスクを回避する

### 1.1.2 表記出典ルール（曖昧変換による誤記を禁止）（v1.4.6）

- `-Xxx`（PowerShell パラメータ表記）は、**スクリプトの `param(...)` 定義に存在するものだけ**を記載する
  - 出典：`make_consult_bundle.ps1` の `param(...)` ブロック
- `--xxx`（Git オプション表記）は、**スクリプトが `DIFF_INDEX.md` に出力する `DiffArgs` に実際に含まれるものだけ**を記載する
  - 出典：生成物ZIP内 `DIFF_INDEX.md` の `DiffArgs: ...`
- 出典を示せない `--xxx` は記載禁止（意味だけ書く場合は `DiffScope` で表現する）
- 目的：`-UnstagedOnly` を `--unstaged-only` のように **想像で書き換える誤記**を構造的に排除する

### 1.1.3 DB 作業時は `db/current/` を最新構造の第一参照とする（v1.6.3）

- DB seed / migration / repository SQL / diagnostics SQL を作成・修正する場合、過去DDL、古い schema ファイル、過去docs、AI記憶を第一根拠にしない
- 最新の実DB構造は `db/current/` 配下のスナップショットを第一参照とする
- `db/current/` と migration / schema / docs が矛盾する場合は、原則として `db/current/` を優先し、差異を docs / TODO に記録する
- DB構造変更を伴う migration / seed 適用後は、`db/current/schema_inventory.sql` を実行し、`db/current/schema_inventory_result.md` と必要な table summary を更新する
- `db/current/` が未整備、古い、または実行エラーと矛盾する場合は、対象テーブルの `information_schema` 診断SQLを `.sql` ファイルとして `db/diagnostics/` 配下に保存し、ユーザー実行結果を確認してから修正する
- 目的：`tb_category_*` から `tb_taxonomy_*` への移行、旧カラム削除、実DBと旧DDLの差異に引きずられた誤 seed / migration を防ぐ

### 1.1.4 SQL 生成物は `.sql` ファイル化し、DB 反映はユーザー手動を原則とする（v1.7.8）

AI が SQL を作成・修正・提示する場合、diagnostics SQL に限定せず、ユーザーが実行する可能性のある SQL は原則としてすべて `.sql` ファイルとして提示・保存対象にする。

対象：

- diagnostics SQL
- seed SQL
- migration SQL
- repair SQL
- verification SQL
- ad hoc investigation SQL
- repository SQL / application query の検証用 SQL
- その他、DB 状態の調査・作成・更新・削除・検証に使う SQL

原則：

- DB 状態を調査する SQL は `.sql` ファイルとして `db/diagnostics/` 配下に保存する
- seed SQL は `.sql` ファイルとして `db/seeds/` 配下に保存する
- migration SQL は `.sql` ファイルとして `db/migrations/` または既存の migration 配置規約に従って保存する
- データ修復・一時補正・検証用 SQL も、実行可能性がある場合は `.sql` ファイルとして保存する
- AI は、ユーザーが実行する SQL をチャット本文のインライン SQL だけで済ませない
- AI が SQL を案内する場合は、実行コマンドではなく、対象 `.sql` ファイルのパス、実行目的、反映後に確認すべき結果を優先して案内する
- SQL の DB 反映は、原則としてユーザーが phpMyAdmin、PowerShell、またはローカルで採用している手順により手動実行する
- AI は、DB 名・接続方法・実行権限が参照束またはユーザー明示で確認できない状態で、`mysql` 等の SQL 直接実行コマンドを提示しない
- SQL 実行コマンドが必要な場合は、DB 名・接続ユーザー・実行方法が確認できていることを前提とし、不明なら Blocking Questions で停止する

例外：

- 仕様説明、比較説明、レビューコメントのための短い SQL 断片はコードブロックで示してよい
- ただし、その SQL をユーザーが実行する前提になった時点で、必ず `.sql` ファイル化する

目的：

- 何を実行したかを後から追跡できる状態にする
- diagnostics / seed / migration などの分類差によるルール抜けを防ぐ
- 未確認の DB 名や環境前提による実行エラー、および誤った DB への反映を防ぐ

### 1.2 意図しないコードの破壊的変更の禁止

- 修正提案は回帰（既存成果物の欠落）を禁止し、破壊的変更は事前明示と承認を必須とする。

### 1.3 禁止事項（AI 側）

- 推測による仕様補完
- 根拠のないコード提案
- 仕様書を無視した実装案
- 仕様確定前のコード提案
- DocSet 更新前のコード提案
- 横断チェックを省略すること
- 不明点を質問せずに進めること

---

## 2. 基本フロー

要求 → 仕様案 → 合意 → ドキュメント → コード → 試験

### 2.0 参照確定（作業開始条件）

- AI は作業開始前に「カテゴリ別の唯一の正（参照束：map / repo / include / diff）」を明言する
- 参照束は map / repo / include / diff のいずれかで提示される（詳細は 2.4 参照束ルール）
- AI は参照束の DocSet を引用して一致確認を行う
- この参照確定が完了するまでは、仕様案・修正案・コード案を提示しない
- AI は INDEX.md の「DocSet」「唯一の正」行を引用して参照確定の完了を宣言する

#### 2.0.1 運用ルール認識（必須）

- 参照束ZIPには 00_ai_consult_operation_rules.md が同梱される前提とする
- AI は着手前に 00_ai_consult_operation_rules.md を最優先で読み、要点を引用して「運用ルール認識完了」を宣言する
- 不明点は推測せず、Blocking Questions を提示して停止する

#### 2.0.2 基盤メンテナンス例外（INDEX.md が存在しない相談）

次の条件をすべて満たす場合に限り、**INDEX.md を用いた参照確定を例外扱い**としてよい。

- 相談内容が「相談基盤そのものの改修」である
  - 対象例：`ai-consult-tools/chatgpt/make_consult_bundle.ps1`、またはその仕様書（`01_make_consult_bundle_spec.md` 等）
- map/repo/include/diff の参照束（生成物ZIP）を前提にせず、スクリプトによる抽出も行っていない
  - そのため **INDEX.md が存在しない**（生成されていない）

この例外時は、次をもって参照確定とする：

- ユーザーが提示した **「基盤メンテZIP」** を「唯一の正」とする（例：`chatgpt_v1.4.5_YYYYMMDDhhmm.zip`）
- AI は着手前に、基盤メンテZIP内の以下を引用して一致確認を行い、**「参照確定完了（基盤メンテ例外）」** を宣言する
  - `00_ai_consult_operation_rules.md` の DocSet/Version
  - 対象スクリプト（例：`make_consult_bundle.ps1`）のヘッダー（DocSet/Version 等）
  - 対象仕様書（例：`01_make_consult_bundle_spec.md`）の DocSet/Version（仕様変更を伴う場合は必須）

基盤メンテZIPの最低同梱物（欠けていたら停止）：

- `00_ai_consult_operation_rules.md`
- 対象スクリプト（例：`make_consult_bundle.ps1`）
- 対象仕様書（例：`01_make_consult_bundle_spec.md`）（仕様変更を伴う場合）

注意：この例外は **基盤メンテナンス相談にのみ適用**し、通常の map/repo/include/diff 相談（参照束ZIP）では従来通り INDEX.md による参照確定を必須とする。

### 2.1 要求提示

- ユーザーが「何をしたいか」を提示する
- 例：機能追加、修正、リファクタリング、仕様変更など

### 2.2 仕様案の提示

- 不明点は必ず質問
- 推測は禁止
- 仕様案は必ず根拠を明示する（既存仕様書・コードなど）
- 仕様案には必ず「受入条件（AC）」を含める（最低3点：正常系/異常系/境界）

### 2.2.1 Blocking Questions（確認必須事項）

- AI は不明点を「Blocking Questions」として明示し、回答が得られるまで作業を停止する
- BQ は次の形式で列挙する：
  - 質問
  - その質問が必要な理由（影響範囲）
  - 回答がない場合に起きるリスク
- BQ が解消されたら、仕様案を更新して再提示する

### 2.3 仕様の合意

- ユーザーが「OK」「それで進めてください」などの承認を行う
- この時点で仕様が確定する

### 2.4 参照束ルール（map / repo / include / diff）

相談・実装は、原則として「参照束（バンドル）」を単位として行う。
参照束は Git と PowerShell スクリプトにより生成された成果物（テキスト/MD/ZIP）を想定する。

- map：repo と同じ収集範囲から作る、include候補を広めに拾うための軽量地図（本文なしの索引参照）
- repo：本文付きの横断査読用（mapでは不足する場合の広い参照）
- include：実装・仕様確定の主戦場（必要最小限の本文参照）
- diff：レビュー用（変更差分の確認）

原則：

- 仕様検討の初期は原則として map を使用し、include に入れる候補ファイルを洗い出す（本文を毎回大量に読ませない）
- map だけでは依存関係や実装本文の確認が不足する場合に限り、repo を使用する
- map / repo で洗い出した候補範囲を手がかりに include で本文根拠とスコープを固定し、精細なチェックと仕様検討を進める
- map は本文根拠ではないため、map束だけを根拠に具体的なコード差分・仕様差分を作らない
- include は必須ではない（影響範囲が小さく、本文根拠がすでに参照束内にある場合はそのまま進行してよい。ただし根拠は常に明示する）
- 実装後の確認は diff を基本とし、差分レビューで品質を担保する

例：
要求 → map（include候補の洗い出し）→ include（本文根拠の固定）→ 仕様案 → 合意 → diff（レビュー）→ 試験

補助例：
要求 → map → repo（mapでは不足する場合の本文付き横断確認）→ include → 仕様案 → 合意 → diff → 試験

#### 2.4.1 参照束の最低要件

参照束には、最低限次を含める：

- INDEX.md（目的、唯一の正、DocSet、含有物の概要）
- TREE.md（フォルダ構造）
- MANIFEST（ファイル一覧）

include 参照束には、次を優先して含める：

- 入口ファイル（route / action / controller など）
- 入口から参照される依存ファイル（renderer / helper / template 等）
- 仕様ドキュメント該当箇所（最小）

#### 2.4.2 ZIP を唯一の正とする（v1.4）

参照束の成果物は **ZIP（`<DocSet>_<Mode>.zip`）を唯一の正**とする。
既定ではスクリプトが ZIP 生成に成功した場合、作業用フォルダ（`consult_case/<DocSet>_<Mode>[_<CaseName>]/_bundle/`）を自動削除し、案件フォルダ直下に ZIP のみを残す（重複と混入事故の抑止）。

- 作業用フォルダ（_bundle）を残したい場合：`-KeepBundleDir`
- include で DocSet 風ディレクトリも取り込みたい場合：`-AllowDocSetFolders`（既定は除外）
- include の利便性（v1.4.1）：
  - 存在しない IncludePaths は警告してスキップされる（実行停止しない）
  - ただし結果が 0 件になる場合は停止（根拠が空のまま進まないため）

#### 2.4.3 カテゴリ別「唯一の正」（最大4参照束）

この運用では、根拠として扱う参照束ZIPを最大4カテゴリまで許可する（map / repo / include / diff）。
ただし **各カテゴリで「唯一の正」は常に1つ**とし、同カテゴリで新しいZIPが提示された場合、古いZIPは無効（参照禁止）とする。

- Map唯一の正：`<DocSet>_map.zip`
- Repo唯一の正：`<DocSet>_repo.zip`
- Include唯一の正：`<DocSet>_include.zip`
- Diff唯一の正：`<DocSet>_diff.zip`

参照優先順位（衝突時）：**Diff > Include > Repo > Map**
Map は include 候補選定用の軽量地図であり、本文根拠ではない。参照束に存在しない事実は推測禁止。矛盾は Blocking Questions で停止する。

補助添付（ログ/スクショ等）は許可するが、最終根拠は参照束ZIPを優先する。

#### 2.4.4 軽量地図（Mode=map）を先に行う理由（原則）

本運用では、原則として **Mode=map（本文なしの軽量地図）を最初に実行**する。

Mode=map は、repo と同じ収集範囲から対象ファイルを集め、本文全文を出力せずに索引情報だけを出す。関係ファイルを確定除外するためではなく、include候補を漏れにくく広めに拾うために使う。
理由は次の通り：

- **ChatGPTに毎回大量の実コード本文を読ませないため**
  - 長いスレッド・巨大diff・patch再生成が重なると、リクエスト消費・トークン消費・長文処理負荷が大きくなる。
- **include対象を選ぶための地図を先に作るため**
  - 部分的な抜粋（include）だけでは、依存関係・呼び出し関係・暗黙の規約を取り違える可能性がある。
  - Mode=map により、ファイル一覧・見出し・シンボル・selector・import/export候補を確認し、include候補を列挙しやすくする。
- **本文根拠が必要な段階を明確に分けるため**
  - map は候補選定用であり、具体的な修正案・diff案の一次根拠にはしない。

Mode=map により洗い出した候補を手がかりとして、次段で **Mode=include** を用い、対象候補を広めに含めた本文確認（仕様の検討・設計・実装方針の確定）へ進む。
Map では不足する場合のみ、従来の **Mode=repo** を本文付き横断スナップショットとして使用する。
実装後の回帰確認は **Mode=diff** を基本とする。

#### 2.4.4.1 Python / `.py` 優先と PowerShell / patch / コードブロック出力の運用（v1.9.5）

既存ファイルの書き換え・新規作成が必要な場合は、原則として **Python スクリプト（`.py`）による書き換えを優先**する。これは、ChatGPT 側で構文チェック・include bundle 由来の対象ファイルコピーに対するドライラン検証・アンカー一致件数確認を実施してから提示しやすくするためである。

`.py` スクリプトを出す場合は、以下も必須とする。

- 既存ファイルの書き換え・新規作成・複数行置換・ルール追記を案内する場合、長い1行PowerShellや本文埋め込みの here-string を第一候補にしない。
- 原則として、ダウンロード可能な `.py` スクリプトを1本だけ作成して提示する。
- `.py` には、対象ファイルの存在確認、重複防止、アンカー未検出時の停止、UTF-8 BOMなし保存を含める。
- スクリプトのファイル名、リンク名、保存名、実行コマンドに記載するファイル名は必ず一致させる。
- 一時 `.py` は commit 対象にしない。適用後は削除し、`git status --short --untracked-files=all` で残存を確認する。
- 実在行をアンカーにする場合、fresh include bundle またはユーザー環境で確認した実在行を省略・言い換え・正規表現化しない。完全一致確認は、実在行をそのまま保持して行単位で検査する。
- 部分一致を使う場合は、なぜ部分一致で安全かを事前に説明し、必要なら Blocking Questions で停止する。
- ChatGPT が `.py` を提示する前に、必ず可能な範囲の事前検証を行う。最低限、`py_compile` による構文チェック、include bundle または diff bundle から復元した対象ファイルコピーへのドライラン適用、アンカー一致件数、2回目実行時の重複防止、変更対象ファイル一覧を確認する。
- `.py` 提示時は、上記の事前検証結果を短く明記する。検証できない項目がある場合は、`.py` 提示前に「何を検証できていないか」を明示し、必要なら Blocking Questions で停止する。
- `.py` を生成しただけで、構文チェック・コピー適用テストを行わないまま「検証済み」と表現してはならない。

PowerShell は完全禁止ではない。ただし、本文編集ではなく次の用途を基本とする。

- `git status`、`git add`、`git commit`、`git push`
- `npm run build`、`php -l` などの確認コマンド
- `make_consult_bundle.ps1` による map / include / diff / repo bundle 生成
- 一時ファイル削除などの短い補助コマンド

patch は完全禁止ではない。ただし、patch は通常の第一候補ではなく、次のいずれかに該当する場合の例外手段として扱う。

- ユーザーが明示的に patch 方式を希望した場合
- 小規模なコード / SCSS / TS / PHP 等の差分で、`git apply --check` による適用確認が容易な場合
- ユーザー環境の実体差分を確認するためのレビュー用成果物として patch が有効な場合

特に、Markdown、長文ドキュメント、日本語を多く含む文書、コードフェンスを含む文書、CRLF / LF 差異の影響を受けやすいファイルでは、patch より Python / `.py` を優先する。

patch を出す場合：

- patch 方式を選んだ理由と、適用前後に実行する確認コマンドを併記する。
- **fresh include bundle** または **fresh diff bundle** に含まれる対象ファイル本文を根拠にする。include bundle の本文が Markdown snapshot として収録されている場合も、対象ファイル全体が確認でき、truncated でないなら patch 生成根拠として使用してよい。
- map / repo 束だけを根拠に、既存ファイルへの patch を出さない。
- patch は、変更前ファイルと変更後ファイルから作った **機械的diff** に限定する。
- 記憶・推測・チャット上の断片・失敗した patch の目視補修だけを根拠に、修正版 patch を再作成しない。
- file_search 抽出表示、チャット上の部分引用、コードブロック本文、途中で切れた snapshot、または truncated な本文を、対象ファイル全体と同一視して patch 生成元にしない。
- patch 提示前に、対象ファイル、実在見出しまたは実在シンボル、変更箇所、変更根拠を先に示す。
- patch 適用時は `git apply --check` を先に実行し、成功した場合だけ `git apply` する。
- include bundle が Markdown snapshot 形式の場合、CRLF / LF、末尾改行、空白だけの行、コードフェンス境界が適用結果に影響する可能性を前提にする。そのため、ユーザー環境で `git apply --check` が通るまでは「適用可能」と断定しない。
- `corrupt patch` / `patch does not apply` 等で失敗した patch は破棄扱いにする。同じ復元方式・同じ抽出表示を元に v2 / v3 patch を繰り返し作らず、失敗原因、対象ファイル本文、不可視文字、fresh include bundle の取り直し、ユーザーのローカル実体から生成された差分・本文、または raw 添付の必要性を確認してから再生成する。
- patch 失敗後にユーザーのローカル実体確認（`git hash-object`、行番号付き本文、`git diff` 等）へ切り替えた場合、その確認済みローカル実体を次 patch の根拠として扱ってよい。
- ただし、確認済みファイルと未確認ファイルを混在させて再生成しない。複数ファイル patch の一部だけ実体確認した場合、未確認ファイルは同じ patch に含めず、追加確認を行うか patch を分割する。
- 複数ファイル patch が失敗した場合は、PHP / SCSS / TS / docs など責務単位で patch を分割し、失敗箇所を切り分けてから再生成する。
- patch 適用後は、原則として staged diff bundle を生成して査読する。

コードブロックを出す場合：

- コードブロックは引き続き使用する。長文であっても、必要な場合は避けずに使う。
- 出力前に、開始フェンスと終了フェンスが対応していることを確認する。
- 本文内に ``` を含む場合は、外側フェンスを ```` 以上にするか、ブロックを分割して Markdown のネスト崩れを避ける。
- PowerShell コマンドは、原則として1行で提示する。
- 長い引き継ぎ文・patch・設定例をコードブロックで出す場合は、説明文をコードブロック内に混ぜず、コピー対象と説明対象を分ける。

目的は patch を完全禁止することではなく、**Python / `.py` 優先・fresh bundle 根拠・機械的生成・事前検証・適用確認・diff bundle 査読**により、壊れた出力を減らすことである。

#### 2.4.5 診断出力（-Diag）の扱い

- `-Diag` はスクリプトの**診断出力（コンソール出力）**を有効化するためのフラグであり、**既定では無効**とする。必要時のみ `-Diag` を付けて実行する。
- `-Diag` はトラブルシュート（生成物欠落／除外判定／Git差分抽出の不整合など）に限って使用し、通常の相談フローでは参照束を冗長化しない。
- `-Diag` を使用した場合は、**実行ログ（コンソール出力の貼り付け）**に「Diag有効化」の旨と目的（何を確認するためか）を明記する。

#### 2.4.6 include 指定（v1.4.5）

- v1.4.5 では `-IncludePaths` に **フォルダ名のみ**（パス区切りなし）も指定できる（同名フォルダが複数ヒットしたら停止）。
- ファイル名のみ指定は従来通り利用できる（同名ファイルが複数ヒットしたら停止）。
- 明示パス指定（例：`src/controllers/HomeController.php`）が最も安全。
- `Mode=include` の `-IncludePaths` は、従来の「パス指定（ファイル/フォルダ）」に加えて **「ファイル名のみ」**を指定できる。
- RepoRoot 直下に実在するファイル/フォルダ名と一致する場合は、ファイル名指定ではなく **パス指定として扱う**（既存互換のため）。
- 同名が複数ヒットした場合は **停止**（曖昧な根拠で進めない）。
- ワイルドカードは今回 **非対応**（`*` / `?` / `[]` を含む指定は停止）。

#### 2.4.7 補助運用ルール（役割分担）の参照先

本章の内容は「8. 補助運用ルール」に移動（統合）した。
重複と散在を防ぐため、以後は 8章を参照する。

---

## 3. 仕様確定後のドキュメントフェーズ

### 3.0 ChatGPT相談フロー（パターンA）

ChatGPT を用いた仕様検討・査読・修正確認は、以下のフローに統一する。

1. 参照確定（作業開始条件の満たし込み）を行う（2.0）
2. 参照束ルールに従い、map / repo / include / diff を使い分けて相談を進める（2.4）
3. map で対象ファイルを特定し、includeコマンドを提示する（AIがコマンドを提示・ユーザーが実行して添付）
4. include bundle を根拠に実装内容を確定し、BQがあれば先に解消する（0.2節）
5. Pythonスクリプト（`.py`）を事前検証してから生成し、htdocs直下への配置・実行コマンドを提示する（8.3節）
6. スクリプト適用後の標準手順（3.0.1節）に従い、チェック・diff bundle確認・一時`.py`削除・commit・pushの順で進める

#### 3.0.1 スクリプト適用後の標準手順（v1.9.5）

Pythonスクリプト適用が成功したら、以下の順で進める。

**ステップ1：変更種別に応じたチェック**

PHPファイルを変更した場合：

```powershell
php -l <変更したPHPファイルのパス>
# 「No syntax errors detected」が出れば成功
```

TypeScript / SCSS を変更した場合：

```powershell
cd C:\xampp\htdocs; npm run build --workspace=<ワークスペースパス>
# 「✓ built in X.XXs」が表示されれば成功
```

Markdown / ドキュメントのみを変更した場合：

```powershell
cd C:\xampp\htdocs; git diff --check
```

**ステップ2：diff bundle を生成してAIに添付**

```powershell
cd C:\xampp\htdocs; pwsh -NoProfile -ExecutionPolicy Bypass -File ai-consult-tools\chatgpt\make_consult_bundle.ps1 -Mode diff -RepoRoot "C:\xampp\htdocs" -CaseName "<相談名>"
```

生成された `.md` または ZIP をAIに添付する。AIは変更内容・漏れ・副作用を確認する。

**ステップ3：使用したPythonスクリプトを削除して残存確認**

この削除コマンドは、スクリプト適用前や diff bundle 確認前には提示しない。スクリプト適用、必要チェック、diff bundle 確認が通り、一時 `.py` が不要と判断できた後に提示する。

```powershell
cd C:\xampp\htdocs; Remove-Item .\<スクリプト名>.py -ErrorAction SilentlyContinue; git status --short --untracked-files=all
```

**ステップ4：問題なければ4.4節のGit確定ルーティンへ進む**

### 3.0.2 includeモードの運用ルール

- include は必須ではない（2.4 の原則に従う）
- 影響範囲が広い／ラリーが長い／参照が散ってきた場合は include を推奨（作業スコープ固定のため）
- include モードは ChatGPT が列挙した「影響範囲のパス一覧」をそのまま渡す（2.4.1 / 3.1.1 / 2.4.6）
- スクリプトはローカルの実ファイルを直接読み取り、統合テキストを生成する（手作業でのコピー集約は不要）

### 3.0.3 diffモードの役割

- diff モードは「実装後の差分確認」にのみ使用する。
- ChatGPT は diff を読むことで、修正内容を **原則として** 把握できる。
- ただし、変更規模が大きい場合や周辺影響の確認が必要な場合は、diff だけでは正確に判断できないことがある。
- その場合、AI は推測せず、必要な参照束（include または repo）の再生成を提案し、Blocking Questions を提示して停止する。
- diff モードの DIFF_INDEX.md は snapshot と同じ構造で読みやすく統一される（v1.3）。

### 3.1 影響範囲の横断チェック

注意：
この節（3.1）は「影響範囲の洗い出し（何を確認し、何を列挙するか）」を扱う。
参照束（map / repo / include / diff）の定義・原則・唯一の正・参照優先順位は 2.4 に従う。
同じ内容を二重に記載して参照揺れを起こさないため、手順側（3章）は必要に応じて 2.4 を参照する。

以下のレイヤーを横断的に確認する：

- API
- DB / モデル
- UI / UX
- 多言語
- 権限
- SEO
- ログ
- 移行
- バリデーション
- エラーハンドリング
- その他、CMS 固有の仕様
- UIテンプレートに渡す変数（context keys / view variables）は「契約」として扱い、変更する場合は仕様案に明記し、互換性と影響範囲を必ず確認する

必要に応じてユーザーにファイル添付を依頼する。

#### 3.1.1 アウトプット

AI は影響範囲チェックの結果として、次を提示する：

- 影響が想定される領域（API / DB / UI / 多言語 / 権限 / SEO / ログ / 移行…）
- 影響がありそうなファイル群（パス付き）
- “確認が必要だが参照束に含まれていないファイル” の追加要求リスト（Blocking Questionsに統合）
- include 参照束としてまとめるべき最小セット案（入口ファイル＋依存ファイル）

### 3.2 ドキュメント修正案・新規作成案の提示

- 修正案は **コピー＆ペースト可能な Markdown** で提示
- DocSet のバージョン更新案も含める
- 新規ドキュメントが必要な場合はその提案も行う

### 3.3 ユーザーによるドキュメント更新

- ユーザーがローカルで修正を反映
- ドキュメントのヘッダーに **DocSet バージョンを更新**
- AI に「更新完了」を伝える

### 3.4 AI によるドキュメント整合性チェック

- 最新 DocSet を基準に整合性を確認
- 問題なければ「仕様書確定」

---

## 4. コードフェーズ（仕様書確定後にのみ実施）

### 4.0 コードフェーズの前提

- 原則として include 参照束を根拠にコード修正案を作成する
- repo 参照束を根拠にコード修正へ進むのは例外（必要時のみ）
- 実装完了後は diff 参照束でレビューを行う（差分レビュー必須）

#### 4.0.1 diff レビューの範囲

- 原則：staged 差分をレビュー対象とする（コミット直前の確定差分）
- 例外：未コミット差分（unstaged）しかない場合は、その差分をレビュー対象とする
- diff 参照束には、対象ファイルごとに「変更理由（意図）」を付記する
- diff 参照束には、対象ファイルごとに「変更理由（意図）」を付記する

### 4.1 コード修正案の提示

- 仕様書に完全準拠
- 推測禁止
- 必要なら追加のコードファイルを要求
- 提案は **コピー＆ペースト可能なコードブロック** で提示
- AI がコードを提示する場合は、必ず「ファイルパス」を併記する
- 原則として「全文」を提示する（ユーザーが diff 指定した場合のみ diff）
- 提示内容はコピペで完結し、依存する省略（…）をしない
- **ファイルの書き換え・新規作成が必要な場合は、コードブロックで提示するのではなく、必ず `.py` スクリプトファイルとして提示する（8.3節に従う）**
  - コードブロック提示は、実行コマンド例・参照用コード断片・AIが内容確認するためのものにとどめる
  - 「コードブロックで全文提示した」だけではスクリプト提示の義務を果たしたことにならない

### 4.2 ユーザーがローカルでコード反映

- エラーが出た場合は AI に相談
- AI はエラー内容をもとに再提案

### 4.3 AI による最終コードチェック

- 問題なければ「コード確定」

### 4.4 Git 確定ルーティン（通常完了条件）（v1.7.7）

コードまたはドキュメントの修正を反映した後は、原則として commit で止めず、push までを通常完了条件とする。
ただし、別件の未追跡ファイル、一時 patch、consult_case 生成物、別AI用作業物などを巻き込まない。

基本手順：

1. 対象ファイル限定で状態確認する。

```powershell
git status --short -- <path1> <path2> ...
```

2. 変更ファイルの種別に応じて以下のチェックを行う。

PHP ファイルを変更した場合：

```powershell
php -l <変更したPHPファイルのパス>
# 例：
php -l <変更したPHPファイルのパス>
```

TypeScript / SCSS を変更した場合：

```powershell
# ビルドコマンドは consult.local.md の「ビルドコマンド」セクションを参照
# 記載がない場合は BQ を立てて停止する
```

ビルドエラーが出た場合は修正してから次へ進む。`✓ built in X.XXs` が表示されれば成功とする。

チェックと diff bundle 確認が通ったら、AIは使用したPythonスクリプトの削除コマンドを提示する。削除コマンドはスクリプト適用前には出さない。

```powershell
cd C:\xampp\htdocs; Remove-Item .\<スクリプト名>.py -ErrorAction SilentlyContinue; git status --short --untracked-files=all
# 例：
cd C:\xampp\htdocs; Remove-Item .\apply_<スクリプト名>.py -ErrorAction SilentlyContinue; git status --short --untracked-files=all
```

3. 新規作成ファイルがある場合：未追跡ファイルを確認してから追跡済みにする。

```powershell
git status --short --untracked-files=all -- <path>
git add <新規ファイルのパス>
```

4. 対象ファイルだけを staged にする。

```powershell
git add <path1> <path2> ...
# 例：
git add <path1> <path2> ...
```

5. staged 差分の基本エラーを確認する。

```powershell
git diff --check --cached -- <path1> <path2> ...
```

出力がなければ問題なし。

6. diff bundle を生成してAIに添付する。

```powershell
cd C:\xampp\htdocs; pwsh -NoProfile -ExecutionPolicy Bypass -File ai-consult-tools\chatgpt\make_consult_bundle.ps1 -Mode diff -RepoRoot "C:\xampp\htdocs" -CaseName "<相談名>"
```

生成された `.md` ファイルをAIに添付する。AI は diff bundle を確認し、変更対象・変更理由・副作用の有無を明示する。

7. 問題がなければ commit する。

```powershell
git commit -m "<type>(<scope>): <summary>"
```

8. commit 後に状態確認する。

```powershell
git status --short -- <path>
git log --oneline -3
```

9. push する。

```powershell
git push origin master
```

10. push 後に `HEAD` と `origin/master` の一致を確認する。

```powershell
git log --oneline -3
```

`HEAD -> master, origin/master, origin/HEAD` が同じコミットを指していれば完了とする。

注意：

- `git status --short --untracked-files=all` は全体把握には有用だが、未追跡ファイルが多い場合は確認対象が埋もれるため、通常確認では対象パスを絞る。
- `git add .`、`git add -A`、対象外ファイルを含む一括 add は原則禁止する。
- 一時 patch は適用後に削除してよいが、`ai-consult-tools/chatgpt/consult_case/` はユーザーが明示しない限り削除しない。
- push 前に別件差分や未追跡ファイルが見えても、今回対象でないものは勝手に整理・削除・stage しない。
- commit / push を行わずに終了する場合は、その理由と未完了の次手順を明記する。

---

## 5. 動作試験フェーズ

### 5.1 AI が試験項目・チェックリストを作成

- 正常系
- 異常系
- 境界値
- 権限
- 多言語
- SEO
- ログ
- 移行
- UI/UX
- API レスポンス
- DB 反映
など、仕様に応じて作成

### 5.2 ユーザーがローカルで試験を実施

- 結果を AI に報告
- 必要なら試験データも AI が作成
- 試験で重大な不具合が出た場合は、原則として直前コミットへ戻してから修正方針を再検討する

### 5.3 試験完了でタスク終了

---

## 6. DocSet 運用ルール

- すべての仕様書・コード提案は **DocSet バージョン** を基準に判断する
- ユーザーがドキュメントを更新するたびに DocSet を更新
- 常に **最新 DocSet** を参照して判断する
- DocSet の更新がない状態でコード修正に進むことは禁止

### 6.1 DocSet 運用ルール（参照束の固定）

- DocSet は仕様・コード・生成物の根拠バージョンであり、必ず一致させる
- 相談では DocSet に加えて「参照束（ZIP/MDの束）」を根拠として固定する
- 参照束は最大4カテゴリ（map / repo / include / diff）まで許可し、各カテゴリで「唯一の正」は常に1つとする（2.4.3 に従う）
- 同カテゴリで新しいZIPが提示された場合、古いZIPは無効（参照禁止）とする
- 参照束の切替（新しいZIP添付など）が発生した場合は、必ず 2.0 参照確定からやり直す
- 参照優先順位（衝突時）：Diff > Include > Repo > Map（2.4.3 に従う）

---

## 7. 禁止事項（AI 側）

本章の内容は「1. 禁止事項 > 1.3 禁止事項（AI 側）」に統合した。
重複と散在を防ぐため、以後は 1.3 を参照する。

---

## 8. 補助運用ルール（役割分担 / 個人名）

### 8.1 AIの役割分担（ChatGPT / Copilot）

- ChatGPT：仕様の整理、横断観点の抜け漏れチェック、文書化、差分レビュー（diff）
- Copilot：IDE上での参照探索（定義ジャンプ・検索）、実装補助、局所修正の反復

原則：

- 仕様・判断・合意の中核は ChatGPT 側で行い、推測を排除する
- コード探索や「どこを見ればよいか」の発掘は Copilot を併用して効率化する
- ただし、最終的な仕様根拠は常に参照束（DocSet一致）で担保する

Copilot の主な用途：

- 影響範囲の探索（参照元/参照先の検索、定義ジャンプ）
- 既存命名・既存パターンの追跡（テンプレ変数、context keys 等）
- 実装の叩き台生成（ただし最終判断は参照束と AC に従う）

### 8.2 個人名の非使用（新規追加）

- このチャット内および関連するすべてのドキュメント・提案において、
  ユーザーの個人名を記載しない
- 呼称が必要な場合は「あなた」「開発者」「ご相談者」など、
  個人を特定しない表現を使用する
- 既存の文書に個人名が含まれる場合は、ユーザーの指示に従い修正する

### 8.3 Pythonスクリプト・PowerShell補助コマンド・patchファイルの配置ルール（v1.9.5）

AIがPythonスクリプト（`.py`）、PowerShell補助コマンド、またはpatchファイル（`.patch`）を生成・提示する場合は、以下に従う。

- **配置場所：RepoRoot直下（`C:\xampp\htdocs\`）**
- ユーザーはダウンロードしたファイルをhtdocs直下に置いて実行する
- `.py` の実行コマンドは常に `cd C:\xampp\htdocs; py <ファイル名>.py` の形式で提示する
- `py` が使えない場合の代替として、`cd C:\xampp\htdocs; python <ファイル名>.py` を併記してよい
- `make_consult_bundle.ps1` など既存PowerShellスクリプトを実行する場合は、当該 `.ps1` の実在パスを指定する
- `ai-consult-tools\chatgpt\consult_case\` などのサブフォルダに配置した一時スクリプトを直接実行対象にしない
- 一時的な作業用スクリプトは作業完了後に削除してよい
- ChatGPT は `.py` をユーザーへ提示する前に、可能な範囲で `py_compile`、対象ファイルコピーへのドライラン適用、アンカー一致件数確認、2回目実行時の重複防止、変更対象ファイル一覧確認を行い、その結果を提示文に明記する
- 既存ファイル改修用 `.py` を提示する場合は、原則としてチャット本文へ長文貼り付けせず、ChatGPT 側で `.py` ファイルを生成し、ダウンロードリンクとして提示する。本文には検証結果、実行コマンド、必要チェック、diff bundle 生成コマンドを簡潔に記載する
- `.py` を提示した同じ応答内に、diff bundle 添付・AI確認後に実行する一時 `.py` 削除コマンドと、削除後の `git status --short --untracked-files=all` 確認コマンドも必ず提示する
- 一時 `.py` の削除コマンドは、スクリプト適用前には提示しない。スクリプト適用、必要チェック、diff bundle 確認が通り、不要と判断した後に提示する
- 削除コマンドは、対象 `.py` を削除した後に `git status --short --untracked-files=all` で残存確認する形で提示する

### 8.4 TODOドキュメント連携ルール（v1.7.7）

このプロジェクトでは、複数のAIと進捗を共有するため、`docs/todo/` 配下のTODOドキュメントを進捗管理の正とする。AIはスレッド開始時・終了時に必ずこのドキュメントと連携する。

#### 8.4.1 スレッド開始時（必須）

新スレッド開始時のinclude bundleには、`00_ai_consult_operation_rules.md` とともに、**現在作業中のフェーズに該当するTODOドキュメント**と `consult.local.md` を必ず含める。

現在の該当ドキュメントは `consult.local.md` の「includeコマンドパターン」セクションを参照してください。

```powershell
# consult.local.md の「TODOドキュメント込み」パターンを使用する
# 記載がない場合はユーザーに確認する
# 例:
# pwsh -File ai-consult-tools\chatgpt\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\xampp\htdocs" -CaseName "<相談名>" -IncludePaths "ai-consult-tools/chatgpt/00_ai_consult_operation_rules.md","ai-consult-tools/chatgpt/consult.local.md","<TODOドキュメントのパス>"
```

AIはTODOドキュメントを読み、現在どのPhaseのどの小作業に相当する相談かを確認・宣言してから作業を開始する。
#### 8.4.2 スレッド終了時（必須）

スレッド内で対応した実装・方針決定・調査結果は、引き継ぎ文を作成する前に、必ず該当TODOドキュメントへ追記・修正する。

手順：

1. スレッド内の作業内容を整理し、該当Phaseの進捗・実装記録・残課題を明確にする
2. TODOドキュメントの該当箇所を更新するスクリプトを作成・実行する
3. 更新内容をcommit・pushする
4. 引き継ぎ文（セクション11）を作成する

この順序を守り、TODOドキュメントの更新なしに引き継ぎ文を作成しない。

#### 8.4.3 引き継ぎ文の指示文テンプレート（v1.9.4）

AIが引き継ぎ文（`02_consult_template.md` セクション11）を作成するときは、出力を **(A) fresh include bundle 生成コマンドの単独コードブロック** と **(B) ZIP添付後に貼る引き継ぎ本文** に必ず分離する。include 生成コマンドを長い引き継ぎ本文・writing block・説明文の中に埋め込まない。

このプロジェクトでは、新スレッド開始時に `00_ai_consult_operation_rules.md`、該当TODOドキュメント、`consult.local.md` を含む include bundle を参照する運用を必須とする。そのため、引き継ぎ文に include 生成コマンドがない場合、新スレッドで運用ルール参照が成立しない。

引き継ぎ時の出力は、ユーザーがまず include bundle 生成コマンドだけをコピーして実行し、その ZIP を添付した後、別に提示された引き継ぎ本文を新スレッド冒頭へ貼り付けられる構成でなければならない。

必須構成：

1. まず、引き継ぎ本文とは別に、具体的な include bundle 生成コマンドだけを単独の `powershell` コードブロックで提示する
2. その後、別ブロックの引き継ぎ本文の文頭に「上の include bundle 生成コマンドを実行し、生成された ZIP を添付します。添付後、この相談を開始してください。」を入れる
3. include コマンドには、少なくとも `00_ai_consult_operation_rules.md`、`consult.local.md`、現在作業中のフェーズに該当するTODOドキュメントを含める
4. 添付 include bundle を唯一の正として参照確定するよう指示する
5. `00_ai_consult_operation_rules.md` を最優先で読み、要点を引用して「運用ルール認識完了」を宣言するよう指示する
6. TODOドキュメントを読み、現在どのPhaseの相談かを確認・宣言するよう指示する
7. 直前スレッドの完了済み作業、残課題、次に確認する内容を具体的に書く
8. すぐに patch / diff を出さず、実在ファイル・実在見出し・実在DOM / selector・変更予定箇所・根拠・Blocking Questions を先に提示するよう指示する

引き継ぎ時に出力する2ブロックの基本形：

(A) fresh include bundle 生成コマンドの単独コードブロックを先に出す。`consult.local.md` の include コマンドパターンを基準に、現在作業用の具体的な include 生成コマンドを書く。

```powershell
cd C:\xampp\htdocs; pwsh -NoProfile -ExecutionPolicy Bypass -File ai-consult-tools\chatgpt\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\xampp\htdocs" -ConfigPath "ai-consult-tools\chatgpt\consult.config.json" -CaseName "<相談名>" -IncludePaths "ai-consult-tools/chatgpt/00_ai_consult_operation_rules.md","ai-consult-tools/chatgpt/consult.local.md","<TODOドキュメントのパス>","<現在作業に必要な実ファイル>"
```

この include 生成コマンドは、ユーザーが安全にコピー＆ペーストできるように、引き継ぎ本文とは分離して提示する。長い引き継ぎ本文・説明文・writing block 等の中に埋め込まず、コマンド単体のコードブロックとして先に出すこと。

(B) ZIP添付後に貼る引き継ぎ本文を、include 生成コマンドとは別ブロックで書く。引き継ぎ本文の冒頭には、次の文を通常本文として書く。

> 上の include bundle 生成コマンドを実行し、生成された ZIP を添付します。添付後、この相談を開始してください。

引き継ぎ本文には、続けて以下の内容を含める。

- 添付する include bundle 内の `ai-consult-tools/chatgpt/00_ai_consult_operation_rules.md` を最優先で精査し、要点を引用して「運用ルール認識完了」を宣言してから着手すること
- `ai-consult-tools/chatgpt/consult.local.md` も確認し、ビルドコマンドや include / diff コマンドパターンを推測しないこと
- 添付 include bundle を唯一の正として参照確定し、TODOドキュメントを読んで現在どのPhaseの相談かを確認・宣言すること
- すぐに patch / diff を出さず、まず以下を提示すること
  1. 実在ファイル一覧
  2. 実在見出し / 実在セレクタ / 実在DOM一覧
  3. 現在のPhase上の位置
  4. 次に変更・確認する予定箇所
  5. その根拠
  6. Blocking Questions
- Blocking Questions がない場合だけ、実ファイルを根拠に修正案へ進むこと

禁止事項：

- include 生成コマンドのない引き継ぎ文を出力しない
- include 生成コマンドを、長い引き継ぎ本文・writing block・説明文の中へ埋め込まない
- 「bundleを生成してください」だけで終わる引き継ぎ文を出力しない
- 添付後に相談が開始されない引き継ぎ文を出力しない
- `consult.local.md` のパターンを確認せず、include コマンドを推測しない
- 現在作業に必要な IncludePaths を確認せず、古い include パターンをそのまま流用しない

---

## 8.5 consult.local.md 参照ルール（v1.9.1）

`consult.local.md` はプロジェクト固有の設定を記載するローカル専用ファイルです（Git管理外）。ChatGPTはスレッド開始時にこのファイルがinclude bundleに含まれている場合、必ず内容を読んで以下の情報を把握してから作業を開始してください。

#### 参照必須の情報

- **ビルドコマンド**：TypeScript / SCSS 変更後のビルドに使用する。記載がない場合はBQで停止する。
- **includeコマンドパターン**：よく使うinclude bundleの生成コマンド。スレッド開始時の参考にする。
- **その他の注意事項**：プロジェクト固有の運用上の注意。
#### 公開リポジトリ push 設定の参照

- `ai-consult-tools` 公開リポジトリへ push する場合は、必ず `consult.local.md` の「公開リポジトリ設定」を確認する。
- 現在の `consult.local.md` では、公開リポジトリURLは `https://github.com/ellese1215/ai-consult-tools`、remote名は `public`、公開対象は `ai-consult-tools/` 配下のみとして記録されている。
- remote名、URL、push対象は推測してはいけない。`consult.local.md` に記録がない、または include bundle に含まれていない場合は Blocking Questions で停止する。
- `C:\xampp\htdocs` はモノレポであるため、公開リポジトリへモノレポ全体を直接 `git push public master` してはいけない。
- subtree / split / 別clone など実際の公開手順が未確認の場合は、push コマンドを出さず Blocking Questions で停止する。

#### consult.local.md がinclude bundleに含まれていない場合

- ビルドコマンドが必要になった時点でBQを立てて停止する。
- 推測でビルドコマンドを例示しない。

---
## 9. このルールの目的

- 仕様と実装のズレをゼロにする
- 推測による誤実装を防ぐ
- DocSet によるバージョン管理で混乱を防ぐ
- 長期開発でも整合性を保つ
- 静かで丁寧な開発プロセスを維持する
- CMS 全体を美しく整えながら育てる

---

## 10. 今後の改訂について

- この 00_ai_consult_operation_rules.md はプロジェクトの最上位に位置する
- 必要に応じて DocSet バージョンを更新しながら改訂する
- 改訂は必ず「仕様 → 合意 → ドキュメント → コード → 試験」の流れに従う
