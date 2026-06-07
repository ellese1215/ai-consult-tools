# 09 ChatGPT相談用テストコマンド一覧 v1.4.8

> File: 09_consult_test_command.md
> Updated: 2026-04-24 00:00
> DocSet: 202604240000
> Version: 1.4.8
> Note: v1.4.8 では Android/Electron/Vite 生成物・バイナリ除外が INDEX.md と SKIPPED.txt に反映されることを確認する。

---

## 0) 事前：作業ディレクトリを RepoRoot に合わせる（任意だけど推奨）

cd C:\xampp\htdocs

- 実行ホストは `pwsh` を使用する（`powershell.exe` / Windows PowerShell 5.1 は非対応）

## 1) Mode=repo（リポジトリ横断スナップショット）

pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode repo -RepoRoot "C:\xampp\htdocs"

## 2) Mode=include（指定パスのみスナップショット）

### 2-a) UTF-8 no BOM の docs を含む include 束確認

pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\xampp\htdocs" -IncludePaths "docs\development\01_shared_ts_scss_goal_and_roadmap.md","docs\development\02_shared_ts_scss_folder_structure_guide.md","docs\development\04_spine_games_android_environment_plan.md"

確認観点:

- `parts/snapshot_docs_part_001.md` の見出し本文が文字化けしていない
- `INDEX.md` の `CommandLine` が `pwsh -File ...` になっている

### 1-a) repo 除外リスト確認（v1.4.8）

Mode=repo 実行後、`INDEX.md` の `Excluded Folders` と `Excluded Extensions` に Android/Electron/Vite 生成物・バイナリ除外が出ていることを確認する。

確認観点:

- `Excluded Folders` に `.gradle`, `build`, `dist`, `out`, `release` が含まれる
- `Excluded Extensions` に `.jar`, `.apk`, `.aab`, `.aar`, `.dex`, `.class`, `.so`, `.idsig`, `.ap_`, `.asar`, `.pak`, `.node` が含まれる
- `SKIPPED.txt` に `gradle-wrapper.jar` の UTF-8 decode warning が出ない

### ※ include の注意（推測排除）

- "admin" のような一般名は同名フォルダが複数ヒットしやすく、曖昧時停止（エラー）になり得る
- 最終的に取り込み対象が 0 件になった場合はエラー停止する（根拠が無い状態で進めない）
- 事故回避のため、動作試験では相対パスを明示する指定を推奨する
- tools/ は除外固定のため tools 配下を include 指定しても最終的に除外される（仕様 01 の 3.4 を参照）

pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\xampp\htdocs" -IncludePaths "common"

## 2.1) Mode=include（ファイル名のみ/フォルダ名のみ：v1.4.5）

### include：フォルダ名のみ（v1.4.5：同名フォルダが1件なら成功）

```powershell
pwsh -File ai-consult-tools/archive/chatgpt/make_consult_bundle.ps1 `
  -Mode include `
  -RepoRoot "C:\xampp\htdocs" `
  -CaseName "inc_foldername_only" `
  -IncludePaths "public_html"
```

※同名フォルダが複数ある場合は停止します。

## admin を含めず確実に成功させたいならこちら

pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\xampp\htdocs" -IncludePaths "common"

## 3) Mode=diff（未コミット差分）

pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode diff -RepoRoot "C:\xampp\htdocs"

### 3-a) Mode=diff（未ステージのみ：v1.4.6）

pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode diff -RepoRoot "C:\xampp\htdocs" -UnstagedOnly

### 3-b) Mode=diff（staged差分）

pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode diff -RepoRoot "C:\xampp\htdocs" -Staged

### テンプレート集（例：コピペして差し替え用）

## Mode=repo（横断スナップショット）

### repo 最短

pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode repo -RepoRoot "C:\xampp\htdocs"

### repo（DocSet風フォルダも探索対象に含める：通常は非推奨）

pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode repo -RepoRoot "C:\xampp\htdocs" -AllowDocSetFolders

### repo（診断出力）

pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode repo -RepoRoot "C:\xampp\htdocs" -Diag

### repo（複数行）

```powershell
pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 `
  -Mode repo `
  -RepoRoot "C:\xampp\htdocs"
```

## Mode=include（範囲指定スナップショット）

v1.4.3:

- パス指定（従来互換・推奨） or ファイル名のみ指定
- ワイルドカード（* ? []）は非対応（指定すると停止）
- ファイル名のみ指定は同名複数ヒットで停止

### include：フォルダ1つ（最短・従来互換）

pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\xampp\htdocs" -IncludePaths "common"

### include：フォルダ複数（従来互換）

pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\xampp\htdocs" -IncludePaths "src","db\schema"

### include：ファイル1つ（相対パス）

pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\xampp\htdocs" -IncludePaths "src\controllers\HomeController.php"

### include：ファイル複数（相対パス）

pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\xampp\htdocs" -IncludePaths "src\controllers\HomeController.php","src\models\User.php"

### include：フォルダ＋ファイルを混在（従来互換）

pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\xampp\htdocs" -IncludePaths "src","src\models\User.php"

### include：絶対パス指定（ファイル/フォルダ混在も可）

pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\xampp\htdocs" -IncludePaths `
  "C:\xampp\htdocs\src",
  "C:\xampp\htdocs\src\models\User.php"

### include：カンマ区切り1文字列（スクリプト側が吸収する想定）

pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\xampp\htdocs" -IncludePaths "src,db\schema"

### include：ファイル名のみ（v1.4.3：同名が1件なら成功）

pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\xampp\htdocs" -IncludePaths "Navigation.php"

### include：ファイル名のみ複数（それぞれ1件に解決できる前提）

pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\xampp\htdocs" -IncludePaths "Loader.php","Navigation.php"

### include：見つからない（WARNINGでスキップ→最終的に0件ならエラー停止）

pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\xampp\htdocs" -IncludePaths "___THIS_FILE_DOES_NOT_EXIST___.php"

### include：ワイルドカード（v1.4.3は非対応→停止）

```powershell
pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\xampp\htdocs" -IncludePaths "*Nav*.php"
```

## Mode=diff（差分バンドル）

- diff=0件なら生成しない（OK: diff=0 (no output generated)）

### diff 最短

pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode diff -RepoRoot "C:\xampp\htdocs"

### diff（未ステージのみ：v1.4.6）

pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode diff -RepoRoot "C:\xampp\htdocs" -UnstagedOnly

### diff（リネーム検出：v1.4.6）

※ v1.4.6 では -M を常に有効化し、DIFF_INDEX.md に Renames（heuristic）を明記する。
※ テスト時は「ファイルを移動（git mv）→中身は最小変更→diff生成→DIFF_INDEXのRenames確認」を行う。

### diff（診断出力）

pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode diff -RepoRoot "C:\xampp\htdocs" -Diag

### diff 出力確認（v1.4.7 回帰防止）

- `INDEX.md` の `## Stats` にある `Groups:` が空でないこと
- `MANIFEST.csv` の group 件数と `INDEX.md` の group 別件数が一致すること

## よくある一連フロー（diff → include → repo）

cd C:\xampp\htdocs
pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode diff -RepoRoot "C:\xampp\htdocs"
pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\xampp\htdocs" -IncludePaths "common","src"
pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode repo -RepoRoot "C:\xampp\htdocs"
