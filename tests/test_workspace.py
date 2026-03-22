"""Tests for snapshotting and diff generation."""

from __future__ import annotations

from pathlib import Path

from devlinker.application.workspace import WorkspaceManager
from devlinker.settings import AppSettings


def test_workspace_diff_detects_added_and_modified_files(tmp_path: Path) -> None:
    working_dir = tmp_path / "workspace"
    working_dir.mkdir()
    file_path = working_dir / "example.txt"
    file_path.write_text("before\n", encoding="utf-8")

    settings = AppSettings.model_validate(
        {
            "agents": {
                "working_dir": str(working_dir),
                "state_dir": str(tmp_path / ".devlinker/state"),
                "preview_dir": str(tmp_path / ".devlinker/previews"),
            }
        }
    )
    settings.prepare_runtime()
    manager = WorkspaceManager(settings)

    before = manager.snapshot(working_dir)
    file_path.write_text("after\n", encoding="utf-8")
    (working_dir / "new.txt").write_text("hello\n", encoding="utf-8")
    after = manager.snapshot(working_dir)

    changes = manager.diff_snapshots(before, after)
    change_types = {change.path: change.change_type.value for change in changes}

    assert change_types["example.txt"] == "modified"
    assert change_types["new.txt"] == "added"
