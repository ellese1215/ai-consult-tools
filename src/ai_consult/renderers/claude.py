from __future__ import annotations

from pathlib import Path

from ai_consult.bundle import BundleCommand, BundleModel
from ai_consult.renderers.common import (
    OutputAdapterError,
    OutputContext,
    OutputResult,
    OutputTarget,
    atomic_bundle_directory,
    build_output_documents,
    exceeds_part_limit,
    render_index,
    render_markdown_csv,
    rendered_content_items,
    validate_no_placeholders,
)


def write_claude_bundle(
    bundle: BundleModel,
    context: OutputContext,
) -> OutputResult:
    if context.target is not OutputTarget.CLAUDE:
        raise OutputAdapterError(
            "Claude adapter requires target=claude"
        )

    documents = build_output_documents(bundle)
    rendered_items = rendered_content_items(bundle)
    names, contents = _plan_parts(
        bundle,
        context,
        documents,
        tuple(item.block for item in rendered_items),
    )

    with atomic_bundle_directory(context, bundle) as (
        temp_directory,
        final_directory,
        label,
    ):
        temp_paths: list[Path] = []

        try:
            for name, content in zip(names, contents, strict=True):
                path = temp_directory / name
                path.write_text(
                    content,
                    encoding="utf-8",
                    newline="\n",
                )
                temp_paths.append(path)
        except OSError as exc:
            raise OutputAdapterError(
                f"cannot create Claude Markdown: {exc}"
            ) from exc

    output_paths = tuple(final_directory / name for name in names)
    return OutputResult(
        target=OutputTarget.CLAUDE,
        bundle_label=label,
        bundle_directory=final_directory,
        output_paths=output_paths,
    )


def _plan_parts(
    bundle: BundleModel,
    context: OutputContext,
    documents,
    blocks: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    label = context.bundle_label(bundle)
    expected_count = 1

    for _ in range(20):
        names = _part_names(label, expected_count)
        preamble = _render_preamble(
            bundle,
            context,
            documents,
            names,
        )
        contents = _split_parts(
            bundle,
            context,
            preamble,
            blocks,
        )
        actual_count = len(contents)

        if actual_count == expected_count:
            final_names = _part_names(label, actual_count)
            final_preamble = _render_preamble(
                bundle,
                context,
                documents,
                final_names,
            )
            final_contents = _split_parts(
                bundle,
                context,
                final_preamble,
                blocks,
            )

            if len(final_contents) == actual_count:
                return final_names, final_contents

        expected_count = actual_count

    raise OutputAdapterError(
        "Claude part planning did not converge"
    )


def _part_names(label: str, count: int) -> tuple[str, ...]:
    if count <= 0:
        raise OutputAdapterError(
            "Claude output requires at least one part"
        )

    if count == 1:
        return (f"{label}.md",)

    return tuple(
        f"{label}_part{index}.md"
        for index in range(1, count + 1)
    )


def _render_preamble(
    bundle: BundleModel,
    context: OutputContext,
    documents,
    output_names: tuple[str, ...],
) -> str:
    if bundle.command is BundleCommand.START:
        document_names = (
            "INDEX.md",
            "REPO_OVERVIEW.md",
            "PROJECT_TREE.md",
            "STRUCTURE_STATUS.md",
            "PATH_INDEX.md",
            "SKIPPED.md",
            "MANIFEST.csv",
        )
    else:
        document_names = (
            "INDEX.md",
            "DIFF_INDEX.md",
            "SKIPPED.md",
            "MANIFEST.csv",
        )

    index = render_index(
        bundle,
        context,
        output_files=output_names,
        document_files=document_names,
        part_files=output_names,
    )
    generated_texts = [index]

    if documents.diff_index is not None:
        generated_texts.append(documents.diff_index)

    validate_no_placeholders(generated_texts)
    sections = [
        "## 参照確定\n",
        f"- DocSet: `{context.docset}`\n",
        f"- Command: `{bundle.command.value}`\n",
        "- Target: `claude`\n",
        "- Output files:\n",
    ]
    sections.extend(f"  - `{name}`\n" for name in output_names)
    sections.extend(["\n", index, "\n"])

    if bundle.command is BundleCommand.START:
        for _, content in documents.start_documents:
            sections.extend([content, "\n"])
    else:
        sections.extend(
            [
                documents.diff_index or "",
                "\n",
                documents.skipped,
                "\n",
            ]
        )

    sections.extend(
        [
            render_markdown_csv("MANIFEST", documents.manifest),
            "\n# CONTENT\n\n",
        ]
    )
    return "".join(sections)


def _split_parts(
    bundle: BundleModel,
    context: OutputContext,
    preamble: str,
    blocks: tuple[str, ...],
) -> tuple[str, ...]:
    parts: list[str] = []
    current = preamble
    current_has_block = False
    part_number = 1

    for block in blocks:
        separator = "" if current.endswith("\n\n") else "\n"
        candidate = current + separator + block

        if exceeds_part_limit(
            candidate,
            max_chars=context.max_chars_per_part,
            max_bytes=None,
        ):
            if current_has_block or current == preamble:
                parts.append(_ensure_trailing_lf(current))
                part_number += 1
                current = _continuation_header(
                    bundle,
                    context,
                    part_number,
                ) + block
                current_has_block = True
                continue

        current = candidate
        current_has_block = True

    parts.append(_ensure_trailing_lf(current))
    return tuple(parts)


def _continuation_header(
    bundle: BundleModel,
    context: OutputContext,
    part_number: int,
) -> str:
    header = (
        f"# CONTENT PART {part_number}\n\n"
        f"- DocSet: `{context.docset}`\n"
        f"- Command: `{bundle.command.value}`\n"
        "- Target: `claude`\n\n"
    )
    validate_no_placeholders((header,))
    return header


def _ensure_trailing_lf(value: str) -> str:
    return value if value.endswith("\n") else value + "\n"
