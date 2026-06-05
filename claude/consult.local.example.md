# consult.local.md（プロジェクト固有設定）

> このファイルはGit管理外です（.gitignore に登録済み）。
> consult.local.example.md をコピーして consult.local.md を作成し、あなたの環境に合わせて編集してください。
> スレッド開始時のinclude bundleに必ず含めることで、AIがビルドコマンド等を推測なく把握できます。

---

## 1. ビルドコマンド

TypeScript / SCSS を変更した後にCSSをビルドするコマンドを記載してください。
AIは4.4節のGit確定ルーティンでこのコマンドを参照します。記載がない場合はBQで停止します。

```powershell
# 例1: npmワークスペース構成の場合
cd C:\your-repo; npm run build --workspace=apps/webs/your-app

# 例2: プロジェクトルートで直接ビルドする場合
cd C:\your-repo\apps\webs\your-app; npm run build

# 例3: その他のビルドツールの場合
# cd C:\your-repo; <ビルドコマンド>
```

**実際のビルドコマンド：**

```powershell
# ここに実際のコマンドを記載してください
```

---

## 2. includeコマンドパターン

よく使うinclude bundleの生成コマンドを記載してください。
スレッド開始時のコマンド選択の参考にします。

### 基本（運用ルール + consult.local.md のみ）

```powershell
cd C:\your-repo; pwsh -NoProfile -ExecutionPolicy Bypass -File ai-consult-tools\claude\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\your-repo" -CaseName "<相談名>" -IncludePaths "ai-consult-tools/claude/00_ai_consult_operation_rules.md","ai-consult-tools/claude/consult.local.md"
```

### TODOドキュメント込み

```powershell
# <TODOドキュメントのパス> を実際のパスに置き換えてください
cd C:\your-repo; pwsh -NoProfile -ExecutionPolicy Bypass -File ai-consult-tools\claude\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\your-repo" -CaseName "<相談名>" -IncludePaths "ai-consult-tools/claude/00_ai_consult_operation_rules.md","ai-consult-tools/claude/consult.local.md","<TODOドキュメントのパス>"
```

### よく使うパターン（任意で追加）

```powershell
# パターン1: <説明>
# cd C:\your-repo; pwsh ... -IncludePaths "..."

# パターン2: <説明>
# cd C:\your-repo; pwsh ... -IncludePaths "..."
```

---

## 3. プロジェクト固有の注意事項（任意）

プロジェクト固有の運用上の注意点があれば記載してください。

- 例：デプロイ前に必ず〇〇を確認する
- 例：〇〇ファイルは直接編集禁止（自動生成ファイル）
- 例：〇〇ブランチには直接pushしない
