# AI相談共通運用ルール

> File: `shared/00_ai_consult_operation_rules.md`
> Updated: 2026-07-24
> Rules revision: 20260724-outroot-boundary-r8
> Scope: Chat / Work / Codexによる仕様検討、実装、レビュー、引き継ぎ

## 1. 正本

正本はローカルの現行Gitリポジトリである。ZIPは、リポジトリを直接読めない相談先へ生成時点の状態を運ぶための資料であり、恒久的な正本ではない。

| 判断対象 | 主な根拠 |
|---|---|
| 共通運用 | 本書 |
| CLI・bundle・出力の技術仕様 | `docs/01_current_spec.md`と現行コード |
| ローカル環境・コマンド | `local/consult.local.md` |
| プロジェクト内の読む順序 | `docs/<project>/README.md` |
| 現在のPhase・未完了事項 | `00_project_status.md`、`todo/current.md` |
| 次の一作業 | `handoff/current.md`または今回の指示文 |
| 仕様・実装事実 | 要件書、設計書、現行コード、試験、必要に応じて実DB |

会話だけを最終仕様にしない。会話で確定した内容は、実装と同じ作業単位で正本文書へ反映する。

同種の新しいbundleが提示されたら古いものは使用しない。添付されているだけの資料を、用途確認なしに今回の正本とみなさない。

## 2. 作業開始前の確認

具体的な提案、編集、コマンド提示、レビュー結論の前に、次を確定する。

1. 今回の目的と完了条件
2. 実際に読めるリポジトリ、branch、commitまたは有効なbundle
3. 対象ファイルと対象外・保護対象
4. 確定仕様と未確定事項
5. 調査、編集、試験、公開など許された作業範囲

Chat、Work、Codexという名称だけからファイル可視範囲を推測しない。現在地、対象パス、Git、HEAD、worktreeを実確認する。

次の事項が結果を変える場合だけ作業を止めて質問する。

- 正本またはbase / targetが確定できない
- 必須の仕様、コード、実DBを読めない
- 既存の未コミット変更と安全に分離できない
- 破壊的変更、削除、公開、外部送信に新しい承認が必要

結果を変えない不足については、対象外または未確認と明記して進める。

## 3. 標準フロー

```text
Chatで自由検討（任意）
→ Workで仕様確定
→ Codexで実装・文書同期・試験
→ Workで最新差分をレビュー
→ ユーザー確認後にcommit
→ commit結果の報告とユーザーの別の確認後にpush
→ 次の相談に必要な場合だけstart bundleを一度生成
```

| 工程 | 渡すもの |
|---|---|
| Chat | 通常は添付不要 |
| リポジトリを読めないWorkで仕様確定 | 短い依頼文、最新start bundle一つ |
| リポジトリを読めるCodexで実装 | 確定した実装指示。bundleは不要 |
| リポジトリを読めないCodexで実装 | 確定した実装指示、最新start bundle一つ |
| Workで実装レビュー | レビュー依頼文、最新review bundle一つ |
| 同じCodexでレビュー指摘を修正 | 番号付き修正事項だけ |

旧ツール配布ZIP、過去bundle、通常ログ、重複資料は次の工程へ渡さない。解決済みまたは本件と無関係な失敗ログも渡さない。ただし、未解決の障害自体を次工程で診断する場合は、再現条件、実行コマンド、判断に必要な最小限のエラー出力だけを渡す。複数ZIPを入れ子にしたhandoff compositeは、明示的な必要がある場合だけ作る。

### 3.1 コマンド提示の共通原則

- ユーザーの実環境と`local/consult.local.md`に従い、ユーザーが一括実行できる完全なコマンドを提示する。
- 実行前提、RepoRoot、対象パスと、実行後に確認すべき出力を明示する。
- 一つの実行単位を一つのコードブロックへ収録し、コードブロック内へ別のコードブロックを入れない。
- stage、commit、pushなど状態を変える工程は必要に応じて分け、直前の結果を確認してから次へ進む。
- 失敗時は原因を確認し、原因未確認のまま同種の巨大コマンドを繰り返さない。
- 外部スクリプトを配布する場合は、対象環境で安全に読める文字コードと構文であることを配布前に確認する。
- 正本文書にある標準CLIで完了できる処理は、そのCLIを直接提示する。状態検査、設定ファイル生成、ZIP検査などを重ねた独自wrapperへ置き換えない。
- 追加検査は、標準CLIで実際に障害が発生し、その原因を切り分ける場合だけ、必要最小限の診断として提示する。

### 3.2 スレッド／タスクの立て直し

- 相談が長大化して判断精度や参照の一貫性が落ちる前に、AI側から立て直しを提案し、ユーザーから尋ねられるまで漫然と継続しない。
- Phase完了、実装単位完了、レビュー完了、次の一作業確定など、論理的な区切りで提案する。
- 引き継ぐ内容は現在状態と次の一作業を中心とし、共通ルール全文や完了済みログを転記しない。bundleが必要な場合だけ最新の一つを用意する。
- 作業途中で安全に完了できる範囲を理由なく放棄して、立て直しを優先しない。

## 4. bundle

ツール配布ZIP、start bundle、review bundleを区別する。

- start bundle：仕様検討・実装開始用の現行資料
- review bundle：基準HEADに対する生成時点のworktree状態（staged、unstaged、未追跡）
- ツール配布ZIP：相談ツール自体を保守する場合だけ使用

### 4.1 start bundleへ収録するもの

引き継ぎ用の`start`では`--include-set common_rules`を必ず指定し、次の最小運用セットを収録する。

```text
ai-consult-tools/README.md
ai-consult-tools/docs/01_current_spec.md
ai-consult-tools/shared/00_ai_consult_operation_rules.md
ai-consult-tools/shared/02_consult_template.md
ai-consult-tools/local/consult.local.md
```

これらは、次の相談先が使用中の相談ツールの役割、現行CLI仕様、共通フロー、依頼形式、ローカル固有条件を確認するための資料である。個別の引き継ぎコマンドで5ファイルを`--include-paths`へ列挙せず、設定済み`common_rules`から収録する。

`--include-paths`には、次のうち実在して今回必要なプロジェクト資料だけを指定する。

- `docs/<project>/README.md`
- `docs/<project>/00_project_status.md`
- `docs/<project>/todo/current.md`
- `docs/<project>/handoff/current.md`
- 次の一作業に必要な要件書・設計書
- 判断に必要な場合だけ対象コードと対象テスト

存在しない任意文書は作成しない。プロジェクト全体、過去bundle、旧ツール、ログ、別案件は収録しない。

`start`が自動生成する次のファイルは手動指定しない。

```text
INDEX.md
REPO_OVERVIEW.md
PROJECT_TREE.md
STRUCTURE_STATUS.md
PATH_INDEX.md
SKIPPED.md
MANIFEST.csv
folder_tree.txt
```

`folder_tree.txt`は、AIとユーザーがRepoRoot内のパスを確認するための補助資料である。`start`はlive inventory snapshotから同名itemをbundle内生成するが、RepoRoot上の永続ファイルとローカル構造インデックスは作成、修復、更新しない。永続資料が`current`、`stale`、`missing`、`invalid`のどの状態でも状態を報告して生成を継続する。

### 4.2 start bundle生成コマンド

Windows / PowerShellの標準形：

```powershell
cd C:\xampp\htdocs

python .\ai-consult-tools\consult.py start `
  --target chatgpt `
  --profile <profile> `
  --case-name <case> `
  --include-set common_rules `
  --include-paths `
    "docs/<project>/README.md" `
    "docs/<project>/00_project_status.md" `
    "docs/<project>/todo/current.md" `
    "docs/<project>/handoff/current.md" `
    "<next-task-required-path>"
```

実際の引き継ぎでは、プレースホルダーを実在値へ置換し、存在しないパスと不要な行を削除した、実行可能なコマンド全文を提示する。

この標準コマンドは`consult.py start`を直接一度実行する一実行単位とする。

- `structure check`または手動の`structure sync`をstartの必須前処理にしない。
- 永続`folder_tree.txt`とローカル構造インデックスを更新するコマンドは`structure sync`だけである。
- `start`自身が現在構造を一度走査し、そのlive snapshotから最新の`folder_tree.txt`をbundle内生成する。手動の`--include-paths`または`--include-set`指定は不要である。
- 永続構造資料の開始時状態と、取得可能な`folder_tree.txt`のprofile内差分を`STRUCTURE_STATUS.md`で確認する。同文書は、startが永続構造資料を変更していないことも明記する。
- 既存の永続`folder_tree.txt`は`start`前後でbyte-identicalである。古い、欠落、形式不正は状態として報告するが、bundle生成の停止理由ではない。
- 設定済み`outputs.chatgpt.outRoot`と`outputs.claude.outRoot`は生成物専用領域である。現在のtarget、tracked／untrackedを問わず、outRoot自体と全子孫を構造走査、start本文、review差分・未追跡収集、構造資料、`MANIFEST.csv`、`SKIPPED.md`から無言で完全除外する。
- outRootはglobや一般の`excludePaths`ではなく、`[`なども文字として扱うリテラルなディレクトリ境界である。兄弟の正規ソースは除外せず、ソースのリポジトリ相対パスと本文を維持する。
- outRootまたは子孫を`--include-paths`、include set、`--target-paths`へ明示指定した場合は、正式成果物を作らずエラー終了する。現在生成した成果物を通知するCLI出力は維持するが後続bundleへ継承せず、既存成果物を削除、移動、上書きしない。
- `common_rules`は引き継ぎ用の標準`start`で必ず指定する。ほかのプロファイル外共通資料が必要な場合は、実在する設定済み`--include-set`を追加する。その場で一時設定ファイルを作るwrapperは提示しない。
- ZIP内部、`MANIFEST.csv`、`SKIPPED.md`など、CLI自身が保証する生成処理をPowerShellで再実装・重複検査しない。実際のCLI障害を診断する場合だけ、問題箇所へ限定して確認する。
- 正常終了、`start: created`、`output:`に加え、ChatGPTでは`bundle_path:`、`bundle_sha256:`、`sidecar_path:`、`sidecar_match: true`を標準の成功条件とする。wrapperは名称を推測せず、この機械可読出力を使用する。

ChatGPT向け正式成果物の標準出力先：

```text
C:\xampp\htdocs\ai-consult-tools\chatgpt\consult_case\<BundleLabel>\<BundleLabel>.zip
C:\xampp\htdocs\ai-consult-tools\chatgpt\consult_case\<BundleLabel>\<BundleLabel>.zip.sha256
```

ChatGPTのstartとreviewはZIPとsidecarの2点を常にセットで生成する。sidecarはUTF-8 BOMなしの`<64桁の大文字SHA-256> *<ZIP basename><CRLF>`という1行だけであり、同一ディレクトリのZIPのhashと照合する。ZIPとsidecarは一時ディレクトリ内で完成・検証してから同時確定され、片方だけの状態を正式成果物として残さない。添付しやすさを理由に出力先を`Downloads`などへ変更しない。

### 4.3 review bundle生成コマンド

```powershell
cd C:\xampp\htdocs

python .\ai-consult-tools\consult.py review `
  --target chatgpt `
  --profile <profile> `
  --case-name <case> `
  --target-paths `
    "<changed-path-1>" `
    "<changed-path-2>"
```

Git変更として確認できる対象パスだけを指定する。削除済みファイルは削除前のRepoRoot相対パスを指定する。review時にstart bundleを作り直さない。

明示した`--target-paths`は、収録項目または`SKIPPED.md`のいずれかで結果を確認できなければならない。Git管理外かつignore対象のローカルファイルも、ファイルパスを完全一致で明示した場合だけ未追跡項目として収録する。ignore対象ディレクトリを指定しても、その配下を再帰的に収録しない。変更がない対象は`no_changes`、存在せずGit変更もない対象は`missing`として`SKIPPED.md`へ記録する。

## 5. 引き継ぎ文

引き継ぎ文には次だけを記載する。

```text
対象プロジェクトと現在のPhase
基準branch / commit
完了した範囲
次に行う一作業
対象文書・対象実装
対象外・保護対象
未解決事項
今回添付する唯一の成果物セット名（ChatGPTはZIPとsidecar）
bundleが必要な場合は、実在値へ置換済みの生成コマンド全文
```

共通ルール全文、過去bundle一覧、完了済み作業の詳細ログは転記しない。

bundleを使用して新しい相談先へ引き継ぐ場合、生成コマンドから`--include-set common_rules`を省略しない。引き継ぎ文へ最小運用セットの本文を転記せず、bundleに収録された正本を読むよう指示する。

## 6. 実装・レビュー・Git

- Codexは編集前に対象ファイル、HEAD、worktree、プロジェクト正本を確認する。
- 確定仕様、実装、正本文書、試験を同じ作業単位でそろえる。
- レビューは正確な基準HEADに対するreview bundle生成時点のworktree状態を対象にし、仕様適合、変更漏れ、副作用、試験を確認する。
- Workでreview bundleをレビューする場合は、本文より先に`DIFF_INDEX.md`、`SKIPPED.md`、`MANIFEST.csv`を確認する。skipまたは収録不足が結論に影響する場合は承認しない。
- 新規、削除、renameでリポジトリ構造が変わる場合は、review bundle生成前に`folder_tree.txt`とローカル構造インデックスの同期可否を確認する。`folder_tree.txt`に今回対象外の既存差分がある場合は上書きせず、同期を保留した理由を完了報告または引き継ぎに明記する。
- 認証、権限、DB、削除、公開範囲、大規模構造変更はWorkの独立レビューを必須とする。
- 軽微な文言、CSS、限定文書修正は、Codexのdiff確認と必要な試験で完了できる。

### 6.1 commit／pushの確認境界

- Codexはcommit前に、変更ファイル、差分概要、review結果、試験結果を報告し、ユーザーの明示的確認前にcommitしない。
- commit前に予定した対象パスだけがstagedであることを照合する。`git add .`とRepoRoot全体への`git add -A`は使わない。
- commit後は結果とcommit IDを報告する。commit完了だけをpush承認とみなさず、ユーザーの別の明示的確認前にpushしない。
- push後はlocal HEADと対象remoteの先端を照合する。commitとpushを一つの無確認処理としてまとめない。
- subtree、公開remote、deployなどは、対象と影響を確認してから個別に進める。

### 6.2 worktree保全

通常の実装・レビュー作業では、Codexは次を独断で実行しない。ユーザーが明示的に依頼した別作業の実施可否は、その作業の対象と影響を改めて確認する。

- `git clean`を使用しない。
- `git reset --hard`を使用しない。
- 対象外変更を`checkout`または`restore`で戻さない。
- 対象外変更を無断で`stash`しない。
- 対象外ファイルを編集、削除、stage、commitしない。
- 既存staged pathと今回のstageを混同しない。
- commit前に予定した対象パスだけがstagedであることを照合する。
- 想定外の対象内変更が見つかった場合は、上書きせず報告する。

## 7. 誤認時の復旧と禁止事項

誤認が判明したら、誤った前提から導いた未確定結論を無効化し、第2章の確認からやり直す。自分の過去回答を現行ファイルより上位に置かない。

次を禁止する。

- 実在確認していないファイル、コマンド、profile、パスの提示
- 現行設定を確認しないbundle出力先の変更
- 旧ツールや過去bundleを通常相談の根拠にすること
- 同種の新旧bundleを同時に有効とすること
- 仕様未確定のまま結果を左右する判断を補完すること
- 運用資料の作成自体を本来の相談・実装・レビューより大きくすること

## 8. 完了条件

- 目的と現在の正本を一文で説明できる
- 合意した変更だけが反映されている
- 仕様、実装、文書、試験が矛盾していない
- 対象外の変更を巻き込んでいない
- 次へ渡す資料が最小構成である
- 次の担当が過去会話を読み直さず一作業を開始できる
