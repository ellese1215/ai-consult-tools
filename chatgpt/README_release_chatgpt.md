# README_release v1.5.0（相談束生成ツール）

> File: README_release.md.

## 1. これは何をするツールか

`make_consult_bundle.ps1` は、ChatGPT 相談用に repo / include / diff の ZIP 束を作成する PowerShell ツールです。相談時に「どのファイルを根拠にするか」を固定し、推測回答や古いファイル参照を減らすことを目的にします。

このツールは安全な共有を補助しますが、秘密情報の完全除外は保証しません。生成ZIPを共有する前に、必ず中身を確認してください。

## 2. 最初に読む順番

AI相談で使う場合、最初に `00_ai_consult_operation_rules.md` を読み、要点を確認してから作業します。このルール文書は軽視しません。

ツール仕様や引数は `01_make_consult_bundle_spec.md` を参照します。秘密情報や公開ZIPの注意点は `shared/SECURITY.md` を参照します。

## 3. 配置例

```text
ai-consult-tools/chatgpt/
  make_consult_bundle.ps1
  consult.config.json
  consult.config.example.json
  consult.local.example.md
  00_ai_consult_operation_rules.md
  01_make_consult_bundle_spec.md
  README_release.md
  SECURITY.md
```

`consult.config.json` が除外ルールと出力先の正です。v1.5.0 では、除外ルールを ps1 内に固定せず、設定ファイルで管理します。

`consult.local.md` はプロジェクト固有のビルドコマンドやincludeコマンドパターンを記載するローカル専用ファイルです。Git管理外にし、公開用には `shared/consult.local.example.md` のみを含めます。

## 4. 最短コマンド

repo 全体確認用です。

```powershell
cd C:\xampp\htdocs; pwsh -NoProfile -ExecutionPolicy Bypass -File ai-consult-tools\chatgpt\make_consult_bundle.ps1 -Mode repo -RepoRoot "C:\xampp\htdocs" -CaseName "repo_check"
```

必要ファイルだけを束ねる include 用です。

```powershell
cd C:\xampp\htdocs; pwsh -NoProfile -ExecutionPolicy Bypass -File ai-consult-tools\chatgpt\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\xampp\htdocs" -CaseName "include_check" -IncludePaths "ai-consult-tools/shared/00_ai_consult_operation_rules.md,ai-consult-tools/chatgpt/make_consult_bundle.ps1"
```

Git差分を束ねる diff 用です。

```powershell
cd C:\xampp\htdocs; pwsh -NoProfile -ExecutionPolicy Bypass -File ai-consult-tools\chatgpt\make_consult_bundle.ps1 -Mode diff -RepoRoot "C:\xampp\htdocs" -CaseName "diff_check"
```

## 5. ConfigPath の扱い

`-ConfigPath` を省略した場合、ツールは次の順に設定ファイルを探します。

```text
1. ai-consult-tools/chatgpt/consult.config.json
2. .consult/consult.config.json
```

明示する場合は次のように指定します。

```powershell
cd C:\xampp\htdocs; pwsh -NoProfile -ExecutionPolicy Bypass -File ai-consult-tools\chatgpt\make_consult_bundle.ps1 -Mode repo -RepoRoot "C:\xampp\htdocs" -ConfigPath "ai-consult-tools\chatgpt\consult.config.json" -CaseName "repo_check"
```

設定ファイルが見つからない場合、ツールは停止します。`consult.config.example.json` をコピーして `consult.config.json` を作成してください。

## 6. consult.local.md の作成

`shared/consult.local.example.md` をコピーして `consult.local.md` を作成し、ビルドコマンド等を記載してください。

```powershell
Copy-Item ai-consult-tools\chatgpt\consult.local.example.md ai-consult-tools\chatgpt\consult.local.md
```

`consult.local.md` はGit管理外のため、コミットされません。スレッド開始時のinclude bundleに含めることで、ChatGPTがビルドコマンドを推測なく把握できます。

## 7. 公開用ZIPに入れるもの

公開用の最小構成は次を推奨します。

```text
make_consult_bundle.ps1
consult.config.example.json
consult.local.example.md
README_release.md
SECURITY.md
01_make_consult_bundle_spec.md
00_ai_consult_operation_rules.md
```

実運用で使う場合は `consult.config.json` も配置します。ただし、個人環境の絶対パスや秘密情報を書いた設定ファイルは公開しないでください。

## 8. 公開用ZIPに入れないもの

詳細は `shared/SECURITY.md` に集約しています。最低限、生成済み `consult_case`、過去の相談ZIP、バックアップZIP、`.env`、秘密鍵、keystore、DB、ログは含めないでください。

## 9. smoke test

差し替え後は、最低限 repo の default/config smoke を確認してください。

```powershell
cd C:\xampp\htdocs; pwsh -NoProfile -ExecutionPolicy Bypass -File ai-consult-tools\chatgpt\make_consult_bundle.ps1 -Mode repo -RepoRoot "C:\xampp\htdocs" -CaseName "public_v150_default_smoke"
```

```powershell
cd C:\xampp\htdocs; pwsh -NoProfile -ExecutionPolicy Bypass -File ai-consult-tools\chatgpt\make_consult_bundle.ps1 -Mode repo -RepoRoot "C:\xampp\htdocs" -ConfigPath "ai-consult-tools\chatgpt\consult.config.json" -CaseName "public_v150_config_smoke"
```
