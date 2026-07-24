from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
POWERSHELL_BLOCK = re.compile(
    r"```powershell\n(.*?)```",
    flags=re.DOTALL,
)
HANDOFF_CORE_PATHS = (
    "ai-consult-tools/README.md",
    "ai-consult-tools/docs/01_current_spec.md",
    "ai-consult-tools/shared/00_ai_consult_operation_rules.md",
    "ai-consult-tools/shared/02_consult_template.md",
    "ai-consult-tools/local/consult.local.md",
)


class OperationDocumentationTest(unittest.TestCase):
    def test_handoff_core_include_set_is_synchronized(self) -> None:
        config_paths = [
            TOOL_ROOT / "config" / "consult.config.example.json",
        ]
        local_config = TOOL_ROOT / "local" / "consult.config.json"

        if local_config.is_file():
            config_paths.append(local_config)

        for path in config_paths:
            with self.subTest(path=path.relative_to(TOOL_ROOT)):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(
                    tuple(payload["includeSets"]["common_rules"]),
                    HANDOFF_CORE_PATHS,
                )

        documentation_paths = (
            TOOL_ROOT / "README.md",
            TOOL_ROOT / "docs" / "01_current_spec.md",
            TOOL_ROOT / "shared" / "00_ai_consult_operation_rules.md",
            TOOL_ROOT / "shared" / "02_consult_template.md",
            TOOL_ROOT / "shared" / "consult.local.example.md",
        )
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in documentation_paths
        )

        for relative_path in HANDOFF_CORE_PATHS:
            self.assertIn(relative_path, combined)

        self.assertIn("--include-set common_rules", combined)
        self.assertIn("引き継ぎ用最小運用セット", combined)

    def test_folder_tree_contract_is_consistent(self) -> None:
        paths = (
            TOOL_ROOT / "README.md",
            TOOL_ROOT / "docs" / "01_current_spec.md",
            TOOL_ROOT / "shared" / "00_ai_consult_operation_rules.md",
            TOOL_ROOT / "shared" / "consult.local.example.md",
        )
        combined = "\n".join(
            path.read_text(encoding="utf-8") for path in paths
        )

        self.assertIn("live inventory snapshot", combined)
        self.assertIn("byte-identical", combined)
        self.assertIn("更新するのは`structure sync`だけ", combined)
        self.assertNotIn(
            "通常のstart bundleへは収録しません",
            combined,
        )
        self.assertNotIn(
            "通常のbundle収録対象またはbundle生成の合否条件にはしない",
            combined,
        )
        self.assertNotIn(
            "`start`が必要に応じて再生成する",
            combined,
        )

    def test_start_sidecar_contract_rejects_legacy_wording(self) -> None:
        paths = (
            TOOL_ROOT / "README.md",
            TOOL_ROOT / "docs" / "01_current_spec.md",
            TOOL_ROOT / "shared" / "00_ai_consult_operation_rules.md",
            TOOL_ROOT / "shared" / "02_consult_template.md",
            TOOL_ROOT / "shared" / "consult.local.example.md",
            TOOL_ROOT / "shared" / "SECURITY.md",
        )
        local = TOOL_ROOT / "local" / "consult.local.md"

        if local.is_file():
            paths += (local,)

        combined = "\n".join(
            path.read_text(encoding="utf-8") for path in paths
        )

        for required in (
            "outputs.chatgpt.outRoot",
            "outputs.claude.outRoot",
            "bundle_path:",
            "bundle_sha256:",
            "sidecar_path:",
            "sidecar_match: true",
            "64桁の大文字SHA-256",
            "ZIP basename",
            "CRLF",
        ):
            self.assertIn(required, combined)

        for forbidden in (
            "`start`もbundle生成前に同じ構造同期",
            "`start`が必要に応じて再生成する",
            "`start`による`folder_tree.txt`の再生成",
            "通常はこのZIP一つだけ",
            "別の検証済み手順でSHA-256 sidecarを生成した場合だけ",
        ):
            self.assertNotIn(forbidden, combined)

    def test_review_contract_covers_explicit_ignored_and_empty_targets(
        self,
    ) -> None:
        rules = (
            TOOL_ROOT
            / "shared"
            / "00_ai_consult_operation_rules.md"
        ).read_text(encoding="utf-8")
        spec = (
            TOOL_ROOT / "docs" / "01_current_spec.md"
        ).read_text(encoding="utf-8")
        combined = rules + "\n" + spec

        for value in (
            "ignore対象",
            "完全なファイルパス",
            "no_changes",
            "missing",
            "SKIPPED.md",
        ):
            self.assertIn(value, combined)

    def test_output_root_contract_is_complete_and_revision_is_synced(
        self,
    ) -> None:
        paths = (
            TOOL_ROOT / "README.md",
            TOOL_ROOT / "docs" / "01_current_spec.md",
            TOOL_ROOT / "shared" / "00_ai_consult_operation_rules.md",
            TOOL_ROOT / "shared" / "02_consult_template.md",
            TOOL_ROOT / "shared" / "consult.local.example.md",
            TOOL_ROOT / "shared" / "SECURITY.md",
        )
        documents = tuple(
            path.read_text(encoding="utf-8") for path in paths
        )
        combined = "\n".join(documents)

        for required in (
            "生成物専用領域",
            "リテラルなディレクトリ境界",
            "tracked／untracked",
            "無言で完全除外",
            "`SKIPPED.md`",
            "明示include",
            "リポジトリ相対パス",
            "既存成果物を削除、移動、上書きしない",
            "`output:`",
            "`bundle_path:`",
        ):
            self.assertIn(required, combined)

        revision = "20260724-outroot-boundary-r8"
        self.assertIn(revision, documents[2])
        self.assertIn(revision, documents[3])
        self.assertNotIn("20260724-start-sidecar-r7", combined)

    def test_local_powershell_examples_are_runnable_when_present(
        self,
    ) -> None:
        local_path = TOOL_ROOT / "local" / "consult.local.md"

        if not local_path.is_file():
            return

        local = local_path.read_text(encoding="utf-8")
        blocks = POWERSHELL_BLOCK.findall(local)
        executable = "\n".join(blocks)

        self.assertGreaterEqual(len(blocks), 5)
        self.assertNotRegex(
            executable,
            r"=\s*@\([^\n]*\)\s*\|\s*Where-Object",
        )
        self.assertNotRegex(
            executable,
            r"=\s*\(git [^\n]+\)\.Trim\(\)",
        )

        for block in blocks:
            with self.subTest(first_line=block.splitlines()[0]):
                self.assertIsNone(re.search(r"<[^>\n]+>", block))
                self.assertEqual(block.count("{"), block.count("}"))

                if re.search(
                    r"(?m)^\s*(?:git|python|npm)\s",
                    block,
                ):
                    self.assertIn("$LASTEXITCODE", block)

        self.assertIn(
            "if ($expectedPublicHead -ne $publicHead)",
            local,
        )
        self.assertIn(
            "$LocalHeadLines = @(git rev-parse --verify HEAD)",
            local,
        )
        self.assertIn(
            "$OriginHeadLines = @(\n    git ls-remote",
            local,
        )

    def test_rule_revisions_are_synchronized(self) -> None:
        expected = "20260724-outroot-boundary-r8"
        rules = (
            TOOL_ROOT
            / "shared"
            / "00_ai_consult_operation_rules.md"
        ).read_text(encoding="utf-8")
        template = (
            TOOL_ROOT / "shared" / "02_consult_template.md"
        ).read_text(encoding="utf-8")

        self.assertIn(expected, rules)
        self.assertIn(expected, template)


if __name__ == "__main__":
    unittest.main()
