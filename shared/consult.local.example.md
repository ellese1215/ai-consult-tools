# consult.local.md（プロジェクト固有設定）

> このファイルはGit管理外です（.gitignore に登録済み）。
> consult.local.example.md をコピーして consult.local.md を作成し、あなたの環境に合わせて編集してください。
> スレッド開始時のinclude bundleに必ず含めることで、AIがビルドコマンド等を推測なく把握できます。

---

## 1. ビルドコマンド

TypeScript / SCSS を変更した後にCSSをビルドするコマンドを記載してください。
AIは00_ai_consult_operation_rules.md の8章でこのコマンドを参照します。記載がない場合はBQで停止します。

```bash
# 例1: npmワークスペース構成の場合
cd <your-repo>; npm run build --workspace=apps/webs/your-app

# 例2: プロジェクトルートで直接ビルドする場合
cd <your-repo>/apps/webs/your-app; npm run build

# 例3: その他のビルドツールの場合
# cd <your-repo>; <ビルドコマンド>
```

**実際のビルドコマンド：**

```bash
# ここに実際のコマンドを記載してください
```

---

## 2. includeコマンドパターン

よく使うinclude bundleの生成コマンドを記載してください。
スレッド開始時のコマンド選択の参考にします。

### 基本（運用ルール + consult.local.md のみ）

```bash
cd <your-repo>; python consult_bundle_claude.py \
  --mode include \
  --repo-root <your-repo> \
  --case-name "<相談名>" \
  --include-paths \
    "ai-consult-tools/claude/00_ai_consult_operation_rules.md" \
    "ai-consult-tools/claude/consult.local.md"
```

### TODOドキュメント込み

```bash
# <TODOドキュメントのパス> を実際のパスに置き換えてください
cd <your-repo>; python consult_bundle_claude.py \
  --mode include \
  --repo-root <your-repo> \
  --case-name "<相談名>" \
  --include-paths \
    "ai-consult-tools/claude/00_ai_consult_operation_rules.md" \
    "ai-consult-tools/claude/consult.local.md" \
    "<TODOドキュメントのパス>"
```

### よく使うパターン（任意で追加）

```bash
# パターン1: <説明>
# cd <your-repo>; python consult_bundle_claude.py --mode include --repo-root <your-repo> --include-paths "..."

# パターン2: <説明>
# cd <your-repo>; python consult_bundle_claude.py --mode include --repo-root <your-repo> --include-paths "..."
```

---

## 3. プロジェクト固有の注意事項（任意）

プロジェクト固有の運用上の注意点があれば記載してください。

- 例：デプロイ前に必ず〇〇を確認する
- 例：〇〇ファイルは直接編集禁止（自動生成ファイル）
- 例：〇〇ブランチには直接pushしない
