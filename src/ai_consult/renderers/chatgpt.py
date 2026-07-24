from __future__ import annotations

import hashlib
import shutil
import zipfile
from pathlib import Path

from ai_consult.bundle import BundleCommand, BundleModel
from ai_consult.renderers.common import (
    OutputAdapterError,
    OutputContext,
    OutputResult,
    OutputTarget,
    PartFile,
    atomic_bundle_directory,
    build_output_documents,
    exceeds_part_limit,
    render_index,
    rendered_content_items,
    validate_no_placeholders,
)


_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def write_chatgpt_bundle(
    bundle: BundleModel,
    context: OutputContext,
) -> OutputResult:
    if context.target is not OutputTarget.CHATGPT:
        raise OutputAdapterError(
            "ChatGPT adapter requires target=chatgpt"
        )

    documents = build_output_documents(bundle)
    parts = _plan_parts(bundle, context)
    part_paths = tuple(part.relative_path for part in parts)

    if bundle.command is BundleCommand.START:
        root_documents = dict(documents.start_documents)
        document_paths = (
            "INDEX.md",
            "REPO_OVERVIEW.md",
            "PROJECT_TREE.md",
            "STRUCTURE_STATUS.md",
            "PATH_INDEX.md",
            "SKIPPED.md",
            "MANIFEST.csv",
        )
    elif bundle.command is BundleCommand.REVIEW:
        root_documents = {
            "DIFF_INDEX.md": documents.diff_index or "",
            "SKIPPED.md": documents.skipped,
        }
        document_paths = (
            "INDEX.md",
            "DIFF_INDEX.md",
            "SKIPPED.md",
            "MANIFEST.csv",
        )
    else:
        raise OutputAdapterError(
            f"unsupported bundle command: {bundle.command.value}"
        )

    internal_paths = document_paths + part_paths
    index = render_index(
        bundle,
        context,
        output_files=internal_paths,
        document_files=document_paths,
        part_files=part_paths,
    )
    root_documents["INDEX.md"] = index
    root_documents["MANIFEST.csv"] = documents.manifest

    entries: list[tuple[str, str]] = []

    for path in document_paths:
        entries.append((path, root_documents[path]))

    entries.extend(
        (part.relative_path, part.content)
        for part in parts
    )
    generated_texts = [index]

    if documents.diff_index is not None:
        generated_texts.append(documents.diff_index)

    validate_no_placeholders(generated_texts)

    with atomic_bundle_directory(context, bundle) as (
        temp_directory,
        final_directory,
        label,
    ):
        archive_path = temp_directory / f"{label}.zip"
        sidecar_path = temp_directory / f"{label}.zip.sha256"
        _write_deterministic_zip(archive_path, entries)
        _verify_archive(archive_path, tuple(path for path, _ in entries))
        archive_sha256 = _calculate_archive_sha256(archive_path)
        _write_sha256_sidecar(
            sidecar_path,
            archive_path,
            archive_sha256,
        )
        verified_sha256 = _verify_sha256_sidecar(
            archive_path,
            sidecar_path,
        )

    final_archive = final_directory / f"{label}.zip"
    final_sidecar = final_directory / f"{label}.zip.sha256"

    if not final_archive.is_file() or not final_sidecar.is_file():
        shutil.rmtree(final_directory, ignore_errors=True)
        raise OutputAdapterError(
            "ChatGPT ZIP and SHA-256 sidecar were not both published"
        )

    return OutputResult(
        target=OutputTarget.CHATGPT,
        bundle_label=label,
        bundle_directory=final_directory,
        output_paths=(final_archive, final_sidecar),
        bundle_path=final_archive,
        bundle_sha256=verified_sha256,
        sidecar_path=final_sidecar,
        sidecar_match=True,
    )


def _plan_parts(
    bundle: BundleModel,
    context: OutputContext,
) -> tuple[PartFile, ...]:
    rendered = rendered_content_items(bundle)
    parts: list[PartFile] = []
    group_items: dict[str, list[str]] = {}

    for item in rendered:
        group_items.setdefault(item.group, []).append(item.block)

    for group, blocks in group_items.items():
        part_number = 1
        current_blocks: list[str] = []

        for block in blocks:
            candidate_blocks = current_blocks + [block]
            candidate = _render_part(
                bundle,
                context,
                group,
                part_number,
                candidate_blocks,
            )

            if current_blocks and exceeds_part_limit(
                candidate,
                max_chars=context.max_chars_per_part,
                max_bytes=context.max_bytes_per_part,
            ):
                parts.append(
                    PartFile(
                        relative_path=_part_path(
                            bundle,
                            group,
                            part_number,
                        ),
                        content=_render_part(
                            bundle,
                            context,
                            group,
                            part_number,
                            current_blocks,
                        ),
                    )
                )
                part_number += 1
                current_blocks = [block]
            else:
                current_blocks = candidate_blocks

        if current_blocks:
            parts.append(
                PartFile(
                    relative_path=_part_path(
                        bundle,
                        group,
                        part_number,
                    ),
                    content=_render_part(
                        bundle,
                        context,
                        group,
                        part_number,
                        current_blocks,
                    ),
                )
            )

    return tuple(parts)


def _part_path(
    bundle: BundleModel,
    group: str,
    part_number: int,
) -> str:
    prefix = (
        "snapshot"
        if bundle.command is BundleCommand.START
        else "diff"
    )
    return f"parts/{prefix}_{group}_part_{part_number:03d}.md"


def _render_part(
    bundle: BundleModel,
    context: OutputContext,
    group: str,
    part_number: int,
    blocks: list[str],
) -> str:
    heading = (
        "SNAPSHOT"
        if bundle.command is BundleCommand.START
        else "DIFF"
    )
    header = [
        f"# {heading} PART",
        "",
        f"- DocSet: `{context.docset}`",
        f"- Command: `{bundle.command.value}`",
        "- Target: `chatgpt`",
        f"- Group: `{group}`",
        f"- Part: {part_number}",
        "",
        "---",
        "",
    ]
    return "\n".join(header) + "\n".join(blocks)


def _write_deterministic_zip(
    archive_path: Path,
    entries: list[tuple[str, str]],
) -> None:
    try:
        with zipfile.ZipFile(
            archive_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
            strict_timestamps=False,
        ) as archive:
            for relative_path, content in entries:
                info = zipfile.ZipInfo(relative_path, _FIXED_ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(
                    info,
                    content.encode("utf-8"),
                    compress_type=zipfile.ZIP_DEFLATED,
                    compresslevel=9,
                )
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise OutputAdapterError(
            f"cannot create ChatGPT ZIP: {exc}"
        ) from exc


def _verify_archive(
    archive_path: Path,
    expected_paths: tuple[str, ...],
) -> None:
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            actual_paths = tuple(archive.namelist())
            bad_entry = archive.testzip()
    except (OSError, zipfile.BadZipFile) as exc:
        raise OutputAdapterError(
            f"cannot verify ChatGPT ZIP: {exc}"
        ) from exc

    if actual_paths != expected_paths:
        raise OutputAdapterError(
            "ChatGPT ZIP entry order or contents are incomplete"
        )

    if bad_entry is not None:
        raise OutputAdapterError(
            f"ChatGPT ZIP contains a corrupt entry: {bad_entry}"
        )


def _calculate_archive_sha256(archive_path: Path) -> str:
    digest = hashlib.sha256()

    try:
        with archive_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise OutputAdapterError(
            f"cannot hash ChatGPT ZIP: {exc}"
        ) from exc

    return digest.hexdigest().upper()


def _sidecar_bytes(archive_path: Path, archive_sha256: str) -> bytes:
    return (
        f"{archive_sha256} *{archive_path.name}\r\n"
    ).encode("utf-8")


def _write_sha256_sidecar(
    sidecar_path: Path,
    archive_path: Path,
    archive_sha256: str,
) -> None:
    try:
        with sidecar_path.open("xb") as stream:
            stream.write(_sidecar_bytes(archive_path, archive_sha256))
    except OSError as exc:
        raise OutputAdapterError(
            f"cannot create ChatGPT SHA-256 sidecar: {exc}"
        ) from exc


def _verify_sha256_sidecar(
    archive_path: Path,
    sidecar_path: Path,
) -> str:
    archive_sha256 = _calculate_archive_sha256(archive_path)
    expected = _sidecar_bytes(archive_path, archive_sha256)

    try:
        actual = sidecar_path.read_bytes()
    except OSError as exc:
        raise OutputAdapterError(
            f"cannot verify ChatGPT SHA-256 sidecar: {exc}"
        ) from exc

    if actual != expected:
        raise OutputAdapterError(
            "ChatGPT SHA-256 sidecar does not match its ZIP"
        )

    return archive_sha256
