# SECURITY

> File: SECURITY.md.

## 1. このツールの安全上の位置づけ

このツールは、AI相談用ZIPを作る補助ツールです。

秘密情報の混入を減らすために `consult.config.json` の除外ルールを使いますが、完全な安全性は保証しません。生成ZIPを共有する前に、必ず中身を確認してください。

## 2. 共有前チェック

共有前に最低限、次を確認してください。

```text
INDEX.md
TREE.md
MANIFEST.csv
SKIPPED.txt
parts/*.md
```

特に `MANIFEST.csv` で、意図しない秘密情報・生成物・大容量バイナリが含まれていないか確認します。

## 3. 公開用ZIPに含めないもの

以下は公開用ZIPやAI相談ZIPに含めないでください。

```text
consult_case/
consult_project/
過去に生成した相談束
実プロジェクトの repo/include/diff ZIP
バックアップZIP
.env
.env.local
.env.production
*.key
*.pem
*.pfx
*.p12
*.jks
*.keystore
id_rsa*
.git-credentials
.npmrc
.pypirc
auth.json
google-services.json
GoogleService-Info.plist
local.properties
key.properties
*.sql
*.sqlite
*.db
*.bak
*.log
```

画像、音声、動画、フォント、ビルド成果物も、相談に必要な場合を除いて含めないでください。

```text
node_modules/
vendor/
dist/
build/
out/
release/
.gradle/
coverage/
*.png
*.jpg
*.jpeg
*.webp
*.gif
*.mp3
*.wav
*.mp4
*.pdf
*.ttf
*.otf
*.woff
*.woff2
```

## 4. consult.config.json の注意

v1.5.0 では、除外ルールの正は `consult.config.json` です。

`excludeFolders`、`excludeExtensions`、`excludeNamePatterns`、`secretNamePatterns` を変更した場合は、必ず repo smoke を実行し、`.git/objects` やフォント・画像・生成済みZIPが混入していないことを確認してください。

```powershell
cd C:\xampp\htdocs; pwsh -NoProfile -ExecutionPolicy Bypass -File tools\chatgpt\make_consult_bundle.ps1 -Mode repo -RepoRoot "C:\xampp\htdocs" -ConfigPath "tools\chatgpt\consult.config.json" -CaseName "security_config_smoke"
```

## 5. 公開配布時の推奨

公開配布では、個人環境向けの `consult.config.json` ではなく、`consult.config.example.json` を同梱してください。

実際のプロジェクトで使う人は、example をコピーして自分の環境向けに調整します。

```powershell
Copy-Item "tools\chatgpt\consult.config.example.json" "tools\chatgpt\consult.config.json" -Force
```
