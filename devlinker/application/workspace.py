"""Workspace preparation, cloning, and diffing helpers."""

from __future__ import annotations

import difflib
import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

from devlinker.domain.enums import ChangeType
from devlinker.domain.models import FileChange
from devlinker.settings import AppSettings


@dataclass
class SnapshotEntry:
    """Internal snapshot data for a single file."""

    digest: str
    content: Optional[str]
    is_binary: bool


class WorkspaceManager:
    """Own the live workspace and preview clones used for manual approval mode."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    @property
    def working_dir(self) -> Path:
        return self._settings.agents.working_dir.resolve()

    def ensure_live_workspace(self) -> Path:
        root = self.working_dir
        root.mkdir(parents=True, exist_ok=True)
        return root

    def clone_for_preview(self, request_id: str) -> Path:
        preview_root = self._settings.agents.preview_dir.resolve()
        preview_root.mkdir(parents=True, exist_ok=True)
        destination = preview_root / request_id
        if destination.exists():
            shutil.rmtree(destination)

        shutil.copytree(
            self.ensure_live_workspace(),
            destination,
            ignore=shutil.ignore_patterns(*self._settings.security.ignored_paths),
            dirs_exist_ok=False,
        )
        return destination

    def cleanup_preview(self, request_id: str) -> None:
        preview_path = self._settings.agents.preview_dir.resolve() / request_id
        if preview_path.exists():
            shutil.rmtree(preview_path)

    def snapshot(self, root: Path) -> Dict[str, SnapshotEntry]:
        snapshots: Dict[str, SnapshotEntry] = {}
        ignore_tokens = tuple(self._settings.security.ignored_paths)

        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue
            relative = file_path.relative_to(root)
            relative_str = relative.as_posix()

            if any(token in relative.parts for token in ignore_tokens):
                continue

            payload = file_path.read_bytes()
            digest = hashlib.sha256(payload).hexdigest()
            is_binary = b"\x00" in payload
            content: Optional[str] = None

            if not is_binary and len(payload) <= self._settings.security.max_file_bytes_for_diff:
                content = payload.decode("utf-8", errors="replace")

            snapshots[relative_str] = SnapshotEntry(
                digest=digest,
                content=content,
                is_binary=is_binary,
            )

        return snapshots

    def diff_snapshots(
        self,
        before: Dict[str, SnapshotEntry],
        after: Dict[str, SnapshotEntry],
    ) -> list[FileChange]:
        changes: list[FileChange] = []
        all_paths = sorted(set(before) | set(after))

        for relative_path in all_paths:
            previous = before.get(relative_path)
            current = after.get(relative_path)

            if previous is None and current is not None:
                changes.append(
                    FileChange(
                        path=relative_path,
                        change_type=ChangeType.ADDED,
                        diff=self._render_diff(relative_path, None, current.content),
                    )
                )
                continue

            if previous is not None and current is None:
                changes.append(
                    FileChange(
                        path=relative_path,
                        change_type=ChangeType.DELETED,
                        diff=self._render_diff(relative_path, previous.content, None),
                    )
                )
                continue

            if previous is None or current is None:
                continue

            if previous.digest == current.digest:
                continue

            changes.append(
                FileChange(
                    path=relative_path,
                    change_type=ChangeType.MODIFIED,
                    diff=self._render_diff(relative_path, previous.content, current.content),
                )
            )

        return changes

    def _render_diff(
        self,
        relative_path: str,
        before_content: Optional[str],
        after_content: Optional[str],
    ) -> str:
        if before_content is None and after_content is None:
            return "No diff available."

        if before_content is None:
            before_lines: Iterable[str] = []
        else:
            before_lines = before_content.splitlines()

        if after_content is None:
            after_lines: Iterable[str] = []
        else:
            after_lines = after_content.splitlines()

        if before_content is None or after_content is None:
            header_before = "/dev/null" if before_content is None else relative_path
            header_after = "/dev/null" if after_content is None else relative_path
        else:
            header_before = header_after = relative_path

        diff = "\n".join(
            difflib.unified_diff(
                list(before_lines),
                list(after_lines),
                fromfile=header_before,
                tofile=header_after,
                lineterm="",
            )
        )
        return diff or "Binary or large file changed."
