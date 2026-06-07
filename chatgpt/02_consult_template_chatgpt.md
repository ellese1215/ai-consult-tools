# ChatGPT相談用テンプレート v1.6.2

> File: 02_consult_template.md
> Updated: 2026-05-13 00:00
> DocSet: 202605130000
> Version: 1.6.2
> Note: v1.6.2 では map を repo と同じ収集範囲から本文なしの軽量地図を作るモードとして明確化する。

---

## 相談：<機能名 or 変更テーマ>

## 参照確定（カテゴリ別：唯一の正）

この相談では「根拠として扱う参照束ZIP」を最大4カテゴリまで許可します（map / repo / include / diff）。
ただし **各カテゴリで唯一の正は常に1つ**です。

- Map唯一の正：`<実在する_map[_<CaseName>].zipファイル名>`（※原則：スレッド開始時点で添付する推奨束）
- Repo唯一の正：未作成（mapでは不足する場合に作成して添付）
- Include唯一の正：未作成（影響範囲抽出後に作成して添付）
- Diff唯一の正：未作成（実装後に作成して添付）

参照優先順位（衝突時）：**Diff > Include > Repo > Map**

運用ルール：参照束内の 00_ai_consult_operation_rules.md に従ってください

重要：

> - 同カテゴリで新しいZIPが提示された場合、古いZIPは無効（参照禁止）です。
> - 参照束の INDEX.md 冒頭（DocSet/唯一の正）を引用して「参照確定完了」を宣言するまで、仕様案・修正案・コード案を出さないでください。
> - 参照束内の 00_ai_consult_operation_rules.md を最優先で読み、要点を引用して「運用ルール認識完了」を宣言してから着手してください。
> - 不明点がある場合は推測せず、Blocking Questions を出して作業停止してください。
> - 参照確定のZIP名は、プレースホルダではなく **実在する生成物ファイル名**で記載してください（混同防止）。

補助添付（別枠）：

> - ログ/スクショ/メモ等の補助資料の添付は可。ただし最終根拠は参照束ZIP。
> - 補助資料が参照束に反映されていない場合は、推測せず「次の参照束に取り込むべき内容」を提示して停止してください。

---

## 1) 相談の種別

- [ ] 仕様変更（既存挙動の変更）
- [ ] 機能追加
- [ ] バグ修正（仕様は変更しない）
- [ ] リファクタ（挙動不変）
- [ ] その他：<>

---

## 2) 目的（なぜやるか）

- 背景：
- 解決したい課題：
- 期待する効果：

---

## 3) 現状（As-Is）

- 現在の挙動：
- 現在の仕様（参照束のどこに書かれているか）：
  - ファイル：`<path>`
  - 該当箇所（見出し/行/キーワード）：
- 既知の制約：
- 関連する既存機能（壊したくないもの）：

---

## 4) 変更後（To-Be）

- 実現したい挙動（ユーザー視点で）：
- 追加/変更する画面・API・データ：
- 互換性方針：
  - [ ] 既存挙動を維持したまま拡張（推奨）
  - [ ] 一部は変更（Breaking Changeの可能性あり → 影響範囲と移行策が必要）

---

## 5) 不変条件（回帰防止：絶対に維持するもの）

- 今回の不変条件：
  1.
  2.
  3.

---

## 6) 受入条件（AC：最低3点：正常系/異常系/境界）

1) 正常系：
2) 異常系：
3) 境界/例外：
（必要なら追加）

---

## 7) AI必須作業（ユーザー記入不要）

AIは必ず次を実施してください（この順で）：

1. 参照確定（INDEX.md冒頭を引用し「唯一の正」を宣言）
2. map参照束を手がかりに、include候補となるファイル・領域を広めに洗い出して列挙
   - map は repo と同じ収集範囲から本文なしで候補を拾う地図であり、関係なし除外の確定根拠にしない
   - 「影響がありそうな領域（未記載含む）」を必ず含める
   - mapだけでは不足する場合は、repoまたはincludeの追加生成を提案し、推測せず Blocking Questions を出して停止
   - map束だけを根拠に具体的なコード差分・仕様差分を作らない
3. 不変条件（回帰防止）と成果物セット欠落の有無を確認
4. Blocking Questions（不明点があればここで停止）
5. 仕様案（根拠：参照束の該当箇所を引用）
6. 承認後に実装方針（※コードは承認後）
   - patch を出す場合は fresh include/diff bundle の実ファイルを根拠にした機械的diffに限定する
   - patch 失敗時は即興修正版を出さず、原因確認または fresh include bundle 取り直しを提案する
   - コードブロックを出す場合は、開始フェンスと終了フェンスの対応、Markdownネスト崩れ、PowerShell 1行提示を確認する
7. 実装後は diff参照束で差分レビュー

（補足）include参照束は「include候補の洗い出し（2）」の後に作成する前提でよい。repo参照束はmapでは不足する場合だけ追加する。diff参照束は実装後に作成する前提でよい。

---

## 8) 再現手順 / テスト手順（ある場合）

- 再現手順：

1.
2.
3.

- 期待結果：
- 実結果（差がある場合）：

---

## 9) 相談したいこと（AIへの依頼）

- 依頼1：include候補の洗い出し（map参照束ベースでIncludePaths候補提示）
- 依頼2：必要なinclude束生成コマンド提示
- 依頼3：include参照束を根拠にした仕様案（根拠つき）＋ Blocking Questions
- 依頼4：仕様合意後、include参照束前提で実装方針（※コードは承認後）
- 依頼5：実装後、diff参照束で差分レビュー

---

## 10) 添付（参照束 / 実行ログ）

### 10.1 参照束ZIP

- スレッド開始時点：
  - 添付：`<実在する_map.zipファイル名>`（推奨：まずは map のみで開始してよい）
  - Repo：未作成（mapでは不足する場合に追加添付）
  - Include/Diff：未作成（include候補洗い出し後／実装後に追加添付）
- 追加添付する場合（必要になったタイミングで追記）：
  - Repo唯一の正：`<実在する_repo.zipファイル名>`（必要な場合のみ）
  - Include唯一の正：`<実在する_include.zipファイル名>`
  - Diff唯一の正：`<実在する_diff.zipファイル名>`

### 10.2 実行コマンドと結果ログ（貼り付け）

- 実行コマンド（map: 実行済）：

```powershell
pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode map -CaseName "php_rename_unique" -RepoRoot "C:\xampp\htdocs"
```

- コマンド例（repo/include/diff: この時点では未実行、必要になったら実行して追記）

```powershell
# repo（mapでは不足する場合の本文付き横断スナップショット）

pwsh -File ai-consult-tools/archive/chatgpt/make_consult_bundle.ps1 -Mode repo -RepoRoot "C:\xampp\htdocs"

# include（ファイル名のみ/フォルダ名のみ指定：v1.4.5）

## 例（フォルダ名のみ）

pwsh -File ai-consult-tools/archive/chatgpt/make_consult_bundle.ps1 `
  -Mode include `
  -RepoRoot "C:\xampp\htdocs" `
  -CaseName "only_public_html" `
  -IncludePaths "public_html"

※同名フォルダが複数ある場合は停止します。狙い撃ちしたい場合は `pavilion-ellese/public_html` のようにパス指定してください。

# diff（実装後の差分レビュー）

pwsh -File ai-consult-tools\archive\chatgpt\make_consult_bundle.ps1 -Mode diff -RepoRoot "C:\xampp\htdocs"
```

- 結果ログ：(貼り付け)

---
