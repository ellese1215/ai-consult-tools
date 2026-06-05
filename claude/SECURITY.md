# SECURITY.md

> File: SECURITY.md
> Version: 1.0.0

このファイルは、`make_consult_bundle.ps1` を使用する際のセキュリティ上の注意事項を説明します。

---

## 1. secret patternsによる自動除外

スクリプトは、`consult.config.json` の `secretNamePatterns` に一致するファイルを**自動的に除外**します。

デフォルトで除外されるパターン（`consult.config.example.json` の既定値）：

| パターン | 対象例 |
|---|---|
| `.env*` | `.env`, `.env.local`, `.env.production` |
| `*.env*` | `app.env`, `database.env` |
| `*secret*` | `secret_key.txt`, `my_secrets.json` |
| `*secrets*.*` | `secrets.yaml`, `app.secrets.json` |
| `*credential*` | `credentials.json`, `aws_credential` |
| `*.pem` | サーバー証明書、SSHキー |
| `*.key` | 秘密鍵ファイル |
| `*.pfx` / `*.p12` | 証明書ファイル |
| `id_rsa*` | SSH秘密鍵 |
| `*.jks` / `*.keystore` | Javaキーストア |
| `key.properties` | Androidビルドキー |
| `local.properties` | ローカル環境設定 |
| `google-services.json` | Firebase設定 |
| `GoogleService-Info.plist` | Firebase設定（iOS） |

---

## 2. 自動除外の限界と注意事項

**secret patternsはファイル名のパターンマッチングです。ファイルの内容は検査しません。**

以下の点に注意してください：

- 機密情報がパターンに一致しないファイル名で保存されている場合は除外されません
- 例：`config.php` の中に APIキーがハードコードされていても除外されません
- バンドル生成前に、出力対象のファイルに機密情報が含まれていないか確認してください

---

## 3. consult.config.json の取り扱い

`consult.config.json` 自体には機密情報を書かないでください。

このファイルには以下のみを記載してください：

- フォルダ名・拡張子・ファイル名パターンのリスト（文字列）
- 出力先パス・運用ルールファイルのパス（相対パス）

APIキー、パスワード、トークン、接続文字列等は記載しないでください。

---

## 4. 生成物（バンドルMD）の取り扱い

バンドルMDはコードの実体を含むため、取り扱いに注意してください：

- バンドルMDはClaudeへの一時的な添付物として使用し、不要になったら削除してください
- `consult_case/` フォルダをGit管理外（`.gitignore`）にすることを推奨します
- バンドルMDを外部に共有する場合は、内容に機密情報が含まれていないことを確認してください

---

## 5. secretNamePatterns のカスタマイズ

プロジェクト固有の機密ファイルがある場合は、`consult.config.json` の `secretNamePatterns` に追加してください。

```json
{
  "secretNamePatterns": [
    ".env*",
    "*.env*",
    "*secret*",
    "*secrets*.*",
    "*credential*",
    "*.pem",
    "*.key",
    "*.pfx",
    "*.p12",
    "id_rsa*",
    "*.jks",
    "*.keystore",
    "key.properties",
    "local.properties",
    "google-services.json",
    "GoogleService-Info.plist",
    "your-custom-pattern*"
  ]
}
```

---

## 6. 脆弱性の報告

このツールに関するセキュリティ上の問題を発見した場合は、Issueまたはリポジトリのコンタクト手段を通じてご報告ください。
