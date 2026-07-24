from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]

COMMON_RULES_PATHS = (
    "ai-consult-tools/shared/00_ai_consult_operation_rules.md",
    "ai-consult-tools/shared/02_consult_template.md",
    "ai-consult-tools/local/consult.local.md",
)
MAINTENANCE_PATHS = (
    "ai-consult-tools/README.md",
    "ai-consult-tools/docs/01_current_spec.md",
    "ai-consult-tools/shared/01_ai_consult_procedures.md",
    "ai-consult-tools/shared/SECURITY.md",
    "ai-consult-tools/shared/consult.local.example.md",
)
STATE_FIELDS = (
    "workflow_schema",
    "case",
    "base_branch",
    "base_commit",
    "source_docset",
    "current_phase",
    "current_gate",
    "current_actor",
    "next_actor",
    "allowed_operations",
    "pending_gates",
    "codex_evidence",
    "work_review",
    "user_decisions",
    "next_single_action",
)
POWERSHELL_BLOCK = re.compile(
    r"```powershell\n(.*?)```",
    flags=re.DOTALL,
)


def read(relative_path: str) -> str:
    return (TOOL_ROOT / relative_path).read_text(encoding="utf-8")


def line_count(text: str) -> int:
    return len(text.splitlines())


class OperationDocumentationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rules = read("shared/00_ai_consult_operation_rules.md")
        cls.procedures = read("shared/01_ai_consult_procedures.md")
        cls.template = read("shared/02_consult_template.md")
        cls.handoff = read("docs/handoff/current.md")
        cls.readme = read("README.md")
        cls.spec = read("docs/01_current_spec.md")
        cls.local_example = read("shared/consult.local.example.md")

    def test_include_sets_are_exact_and_synchronized(self) -> None:
        config_paths = [
            TOOL_ROOT / "config" / "consult.config.example.json",
        ]
        local_config = TOOL_ROOT / "local" / "consult.config.json"
        if local_config.is_file():
            config_paths.append(local_config)

        payloads = []
        for path in config_paths:
            with self.subTest(path=path):
                payload = json.loads(path.read_text(encoding="utf-8"))
                payloads.append(payload)
                self.assertEqual(
                    tuple(payload["includeSets"]["common_rules"]),
                    COMMON_RULES_PATHS,
                )
                self.assertEqual(
                    tuple(
                        payload["includeSets"]["ai_consult_maintenance"]
                    ),
                    MAINTENANCE_PATHS,
                )
                self.assertEqual(
                    tuple(payload["includeSets"]["repository_structure"]),
                    ("docs/REPOSITORY_STRUCTURE.md",),
                )

        if len(payloads) == 2:
            self.assertEqual(
                payloads[0]["includeSets"],
                payloads[1]["includeSets"],
            )

    def test_top_level_contract_assigns_all_responsibilities(self) -> None:
        expected_by_actor = {
            "Work": (
                "read-only調査",
                "仕様確定",
                "進行管理",
                "Codexへの限定指示",
                "独立レビュー",
                "完了判定",
            ),
            "Codex": (
                "実リポジトリ調査",
                "Git管理対象の編集",
                "文書同期",
                "試験",
                "変更証跡作成",
            ),
            "User": (
                "方針承認",
                "stage",
                "commit",
                "push",
                "外部状態変更",
            ),
        }

        for actor, responsibilities in expected_by_actor.items():
            with self.subTest(actor=actor):
                actor_line = next(
                    line
                    for line in self.rules.splitlines()
                    if line.startswith(f"- {actor}は")
                )
                for responsibility in responsibilities:
                    self.assertIn(responsibility, actor_line)

    def test_mandatory_gate_and_completion_evidence_are_explicit(self) -> None:
        gate_order = (
            "Work仕様確定",
            "Codex変更・試験・チェックポイント作成",
            "Work独立レビュー",
            "Userのstage／commit判断",
            "Userのpush判断と必要なremote照合",
        )
        positions = [self.rules.index(value) for value in gate_order]
        self.assertEqual(positions, sorted(positions))
        self.assertIn(
            "Codex証跡と同じreview targetへのWork承認がそろった時点",
            self.rules,
        )
        review_completion = self.rules.split(
            "Workレビューゲートの完了条件：",
            maxsplit=1,
        )[1].split("変更工程全体の完了条件：", maxsplit=1)[0]
        self.assertIn("Codex変更・試験証跡", review_completion)
        self.assertIn("同じreview target", review_completion)
        self.assertIn("Work承認", review_completion)

    def test_minor_change_review_bypass_and_old_revision_are_absent(
        self,
    ) -> None:
        active_documents = (
            self.rules,
            self.procedures,
            self.template,
            self.handoff,
            self.readme,
            self.spec,
            self.local_example,
        )
        forbidden = (
            "軽微な文言、CSS、限定文書修正は",
            "Workレビュー省略",
            "20260724-outroot-boundary-r8",
        )
        for document in active_documents:
            for phrase in forbidden:
                self.assertNotIn(phrase, document)

    def test_template_defines_structured_checkpoint_schema(self) -> None:
        state_block = self.template.split(
            "```yaml\n",
            maxsplit=1,
        )[1].split("```", maxsplit=1)[0]

        for field in STATE_FIELDS:
            with self.subTest(field=field):
                self.assertRegex(
                    state_block,
                    rf"(?m)^{re.escape(field)}:",
                )

        work_review = state_block.split(
            "work_review:",
            maxsplit=1,
        )[1].split("user_decisions:", maxsplit=1)[0]
        self.assertRegex(work_review, r"(?m)^  status:")
        self.assertRegex(work_review, r"(?m)^  evidence:")

        user_decisions = state_block.split(
            "user_decisions:",
            maxsplit=1,
        )[1].split("next_single_action:", maxsplit=1)[0]
        for value in (
            "  policy:",
            "  commit:",
            "    result_commit:",
            "  push:",
            "    remote_commit:",
        ):
            self.assertIn(value, user_decisions)
        self.assertGreaterEqual(user_decisions.count("    evidence:"), 2)

        for document in (
            self.rules,
            self.procedures,
            self.template,
            self.handoff,
        ):
            self.assertNotRegex(
                document,
                r"(?m)^work_review:\s+(?:pending|approved|changes_requested)$",
            )

        for section in (
            "## A. Workで仕様を確定する",
            "## B. Codexへ変更を依頼する",
            "## C. Workへ独立レビューを依頼する",
            "## D. thread／taskを引き継ぐ",
        ):
            self.assertIn(section, self.template)

        review_section = self.template.split(
            "## C. Workへ独立レビューを依頼する",
            maxsplit=1,
        )[1].split("## D.", maxsplit=1)[0]
        for value in (
            "Base HEAD",
            "Target",
            "Acceptance criteria",
            "Review bundle",
        ):
            self.assertIn(value, review_section)

    def test_current_handoff_is_correction_review_checkpoint(self) -> None:
        required_lines = (
            "workflow_schema: ai-consult-workflow/v1",
            "case: ai_consult_work_codex_gate_and_docs_compaction",
            "base_branch: master",
            "base_commit: 2153db0425dd4c68543ae22cd723f2b4c707b9c4",
            "source_docset: 20260724170609",
            "current_phase: document model correction review",
            "current_gate: work independent re-review",
            "current_actor: Work",
            "next_actor: User（承認時。修正要求時はCodexへ戻す）",
            "  - D-1 review bundleと今回のcorrection review bundleを用いたread-onlyレビュー",
            "  status: pending",
            "  evidence: null",
            "    result_commit: null",
            "    remote_commit: null",
            "next_single_action: 今回のcorrection review bundleを、D-1 review bundleと合わせてWorkが独立再レビューする",
        )
        for line in required_lines:
            self.assertIn(line, self.handoff)

        for gate in (
            "Work独立再レビュー",
            "ユーザーのstage／commit判断",
            "ユーザーのpush判断",
            "後続の機械的ゲート実装要否判断",
        ):
            self.assertIn(gate, self.handoff)

        for path in (
            "ai-consult-tools/README.md",
            "ai-consult-tools/local/consult.local.md",
            "ai-consult-tools/shared/00_ai_consult_operation_rules.md",
            "ai-consult-tools/tests/test_operation_docs.py",
        ):
            self.assertIn(path, self.handoff)

        self.assertNotIn("bundle_path:", self.handoff)
        self.assertNotIn("bundle_sha256:", self.handoff)
        self.assertNotIn("sidecar_path:", self.handoff)

    def test_handoff_is_codex_checkpoint_not_live_state(self) -> None:
        self.assertIn(
            "Codexがreview targetをWorkへ渡す時点で作成するGit内の最新工程チェックポイント",
            self.rules,
        )
        self.assertIn(
            "Codexがreview targetをWorkへ渡す時点で作成するGit内の最新工程チェックポイント",
            self.handoff,
        )
        self.assertIn(
            "後続結果を常時反映するlive stateにはしない",
            self.rules,
        )
        self.assertIn(
            "Work承認、commit、pushの後続結果を常時反映するlive stateではない",
            self.handoff,
        )

        for document in (
            self.rules,
            self.procedures,
            self.template,
            self.handoff,
        ):
            self.assertNotIn(
                "`handoff/current.md`を現在状態の唯一の正本",
                document,
            )
            self.assertNotIn(
                "工程移行のたびにactor、gate、pending gates",
                document,
            )

    def test_work_remains_read_only_and_does_not_sync_git_state(
        self,
    ) -> None:
        work_line = next(
            line
            for line in self.rules.splitlines()
            if line.startswith("- Workは")
        )
        self.assertIn("read-only調査", work_line)

        work_review_section = self.rules.split(
            "## 6. Work独立レビュー",
            maxsplit=1,
        )[1].split("## 7.", maxsplit=1)[0]
        self.assertIn("Git管理ファイルを編集せず", work_review_section)

        work_template = self.template.split(
            "## A. Workで仕様を確定する",
            maxsplit=1,
        )[1].split("## B.", maxsplit=1)[0]
        self.assertIn("Git管理ファイルは編集しない", work_template)

        for document in (
            self.rules,
            self.procedures,
            self.template,
        ):
            self.assertNotIn(
                "問題がなければwork_reviewをapprovedへ更新",
                document,
            )
            self.assertNotIn(
                "Workはread-only調査を完了し、共通工程状態を次へ更新",
                document,
            )

    def test_post_review_transition_table_is_finite(self) -> None:
        transition_section = self.procedures.split(
            "工程遷移を次へ統一する。",
            maxsplit=1,
        )[1].split(
            "`changes_requested`の場合だけ",
            maxsplit=1,
        )[0]
        transitions: dict[str, str] = {}
        for line in transition_section.splitlines():
            if not line.startswith("|") or line.startswith("|---"):
                continue
            cells = tuple(cell.strip() for cell in line.strip("|").split("|"))
            if cells[0] == "From":
                continue
            transitions[cells[0]] = cells[2]

        self.assertEqual(
            transitions,
            {
                "Codex handoff": "Work review",
                "Work changes requested": "Codex correction",
                "Work approved": "User commit decision",
                "Commit completed": "User push decision",
                "Push verified": "completed",
            },
        )
        self.assertEqual(
            tuple(
                source
                for source, target in transitions.items()
                if target == "Codex correction"
            ),
            ("Work changes requested",),
        )
        self.assertNotIn("checkpoint sync", transitions.values())
        self.assertIn(
            "`approved`の場合は状態同期を挟まずUserへ進み",
            self.procedures,
        )

    def test_commit_and_push_results_do_not_mutate_checkpoint(self) -> None:
        commit_section = self.procedures.split(
            "## 8. commit前後",
            maxsplit=1,
        )[1].split("## 9.", maxsplit=1)[0]
        push_section = self.procedures.split(
            "## 9. push前後",
            maxsplit=1,
        )[1].split("## 10.", maxsplit=1)[0]

        self.assertIn("result_commit", commit_section)
        self.assertIn(
            "commit結果の同期だけを目的として`handoff/current.md`を更新しない",
            commit_section,
        )
        self.assertIn("remote_commit", push_section)
        self.assertIn(
            "push結果の同期だけを目的として`handoff/current.md`を更新しない",
            push_section,
        )

    def test_base_and_result_commit_fields_have_distinct_roles(self) -> None:
        for document in (
            self.rules,
            self.procedures,
            self.template,
        ):
            self.assertIn("base_commit", document)
            self.assertIn("result_commit", document)
            self.assertIn("remote_commit", document)

        self.assertIn(
            "`base_commit`はreview targetを作成した基準HEADとして固定",
            self.rules,
        )
        self.assertIn(
            "`base_commit`はreview target内で不変",
            self.template,
        )
        self.assertIn(
            "新たな実質的変更サイクルを開始するときだけ",
            self.rules,
        )

    def test_effective_state_sources_have_explicit_priority(self) -> None:
        recovery_section = self.rules.split(
            "## 3. 有効な工程状態の復元",
            maxsplit=1,
        )[1].split("## 4.", maxsplit=1)[0]
        for value in (
            "最新のCodex作成チェックポイント",
            "Codex最終報告とreview bundle",
            "最新のWorkレビュー結果",
            "stage／commit／push結果",
            "branch、HEAD、status、remote照合結果",
            "実リポジトリの事実を最優先",
        ):
            self.assertIn(value, recovery_section)
        self.assertIn(
            "証跡同士を同じreview targetへ結び付けられない場合",
            recovery_section,
        )

    def test_document_roles_are_separated(self) -> None:
        self.assertGreaterEqual(line_count(self.readme), 120)
        self.assertLessEqual(line_count(self.readme), 160)
        self.assertIn("## 文書索引", self.readme)
        self.assertNotIn("source_sha256", self.readme)
        self.assertNotIn("PreviousPath", self.readme)

        self.assertGreaterEqual(line_count(self.spec), 500)
        self.assertLessEqual(line_count(self.spec), 570)
        for value in (
            "## 3. CLI",
            "## 4. 共通設定",
            "## 6. 構造管理",
            "## 7. 共通bundle契約",
            "## 10. エラーと終了コード",
            "## 11. 旧版互換入口",
        ):
            self.assertIn(value, self.spec)
        self.assertNotIn("修正ラリー", self.spec)

        for value in (
            "## 3. start bundle",
            "## 6. review bundle",
            "## 7. Work独立レビューと修正ラリー",
            "## 8. commit前後",
            "## 9. push前後",
            "## 11. thread／taskの立て直し",
        ):
            self.assertIn(value, self.procedures)

        local_path = TOOL_ROOT / "local" / "consult.local.md"
        if local_path.is_file():
            local = local_path.read_text(encoding="utf-8")
            self.assertGreaterEqual(line_count(local), 60)
            self.assertLessEqual(line_count(local), 100)
            self.assertIn("local/runbooks/ai_consult_tools_publish.md", local)
            self.assertNotIn("git push origin master", local)

        self.assertGreaterEqual(line_count(self.local_example), 60)
        self.assertLessEqual(line_count(self.local_example), 100)
        self.assertIn("local/runbooks/<topic>.md", self.local_example)

    def test_include_set_usage_is_documented_by_use_case(self) -> None:
        for document in (
            self.procedures,
            self.readme,
            self.local_example,
        ):
            self.assertIn("--include-set common_rules", document)
            self.assertIn("--include-set ai_consult_maintenance", document)

        maintenance_section = self.procedures.split(
            "AI相談ツール自体の保守",
            maxsplit=1,
        )[1]
        self.assertIn(
            "ai-consult-tools/docs/handoff/current.md",
            maintenance_section,
        )

    def test_technical_contracts_remain_in_the_spec(self) -> None:
        for value in (
            "outputs.chatgpt.outRoot",
            "outputs.claude.outRoot",
            "生成物専用領域",
            "リテラルなディレクトリ境界",
            "tracked／untracked",
            "無言で完全除外",
            "既存bundle、ZIP、sidecar、Claude Markdown、一時成果物は削除、移動、上書きしない",
            "bundle_path:",
            "bundle_sha256:",
            "sidecar_path:",
            "sidecar_match: true",
            "64桁の大文字SHA-256",
            "CRLF",
            "同一入力と同一出力コンテキストから同一バイト列",
            "previous_path",
            "source_sha256",
            "no_changes",
            "missing",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.spec)

    def test_folder_tree_contract_has_one_technical_source(self) -> None:
        for value in (
            "更新するのは`structure sync`だけ",
            "live inventory snapshot",
            "byte-identical",
            "bundle生成の停止条件にしない",
        ):
            self.assertIn(value, self.spec)

        self.assertIn(
            "`folder_tree.txt`の開始時状態を確認",
            self.procedures,
        )
        self.assertIn(
            "既存差分がある場合：`structure sync`を実行せず",
            self.procedures,
        )

    def test_common_rules_size_is_bounded(self) -> None:
        documents = [
            self.rules,
            self.template,
        ]
        local_path = TOOL_ROOT / "local" / "consult.local.md"
        if local_path.is_file():
            documents.append(local_path.read_text(encoding="utf-8"))

        total_lines = sum(line_count(document) for document in documents)
        total_bytes = sum(
            len(document.encode("utf-8")) for document in documents
        )

        if local_path.is_file():
            self.assertGreaterEqual(total_lines, 250)
        self.assertLessEqual(total_lines, 380)
        self.assertLessEqual(total_bytes, 24_000)

    def test_publish_commands_moved_to_on_demand_runbook(self) -> None:
        local_path = TOOL_ROOT / "local" / "consult.local.md"
        runbook_path = (
            TOOL_ROOT
            / "local"
            / "runbooks"
            / "ai_consult_tools_publish.md"
        )
        if not local_path.is_file():
            return

        local = local_path.read_text(encoding="utf-8")
        runbook = runbook_path.read_text(encoding="utf-8")
        for value in (
            "git push origin master",
            "git subtree split --prefix=ai-consult-tools master",
            "git subtree push",
            "git remote add public",
            "if ($expectedPublicHead -ne $publicHead)",
        ):
            self.assertNotIn(value, local)
            self.assertIn(value, runbook)

        for block in POWERSHELL_BLOCK.findall(local + "\n" + runbook):
            with self.subTest(first_line=block.splitlines()[0]):
                self.assertIsNone(re.search(r"<[^>\n]+>", block))
                self.assertEqual(block.count("{"), block.count("}"))
                if re.search(r"(?m)^\s*(?:git|python|npm)\s", block):
                    self.assertIn("$LASTEXITCODE", block)


if __name__ == "__main__":
    unittest.main()
