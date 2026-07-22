from __future__ import annotations

import re
import unittest
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
POWERSHELL_BLOCK = re.compile(
    r"```powershell\n(.*?)```",
    flags=re.DOTALL,
)


class OperationDocumentationTest(unittest.TestCase):
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

        self.assertIn("bundleへ自動収録", combined)
        self.assertIn("合否条件にしない", combined)
        self.assertNotIn(
            "通常のstart bundleへは収録しません",
            combined,
        )
        self.assertNotIn(
            "通常のbundle収録対象またはbundle生成の合否条件にはしない",
            combined,
        )

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
        expected = "20260722-simplified-r4"
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
