"""Tests for Codex command construction."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from devlinker.application.workspace import WorkspaceManager
from devlinker.domain.enums import ExecutionStatus
from devlinker.domain.models import AgentPromptRequest, ExecutionContext
from devlinker.infrastructure.agents.codex_cli import CodexCLIAdapter
from devlinker.infrastructure.agents.process import AsyncSubprocessRunner
from devlinker.settings import AppSettings


def test_build_command_includes_expected_codex_flags(tmp_path: Path) -> None:
    settings = AppSettings.model_validate(
        {
            "agents": {
                "working_dir": str(tmp_path / "workspace"),
                "state_dir": str(tmp_path / ".devlinker/state"),
                "preview_dir": str(tmp_path / ".devlinker/previews"),
                "codex": {
                    "command": "codex",
                    "model": "gpt-5-codex",
                    "extra_args": ["--search"],
                },
            }
        }
    )
    settings.prepare_runtime()

    adapter = CodexCLIAdapter(
        settings=settings,
        codex_settings=settings.agents.codex,
        runner=AsyncSubprocessRunner(),
        workspace_manager=WorkspaceManager(settings),
    )
    request = AgentPromptRequest(
        prompt="build a feature",
        source_channel="cli",
        user_id=0,
        username="cli",
    )
    execution = ExecutionContext(
        working_dir=settings.agents.working_dir,
        timeout_seconds=600,
        write_enabled=True,
        preview_only=False,
        live_workspace=settings.agents.working_dir,
    )

    command = adapter.build_command(
        request=request,
        execution=execution,
        output_file=settings.agents.state_dir / "last.txt",
    )

    assert command[:2] == ["codex", "exec"]
    assert "--json" in command
    assert "--ephemeral" in command
    assert "--search" in command
    assert "workspace-write" in command


def test_read_only_run_skips_workspace_snapshots(tmp_path: Path) -> None:
    settings = AppSettings.model_validate(
        {
            "agents": {
                "working_dir": str(tmp_path / "workspace"),
                "state_dir": str(tmp_path / ".devlinker/state"),
                "preview_dir": str(tmp_path / ".devlinker/previews"),
            }
        }
    )
    settings.prepare_runtime()
    runner = AsyncSubprocessRunner()
    workspace_manager = WorkspaceManager(settings)
    adapter = CodexCLIAdapter(
        settings=settings,
        codex_settings=settings.agents.codex,
        runner=runner,
        workspace_manager=workspace_manager,
    )
    request = AgentPromptRequest(
        prompt="count files",
        source_channel="cli",
        user_id=0,
        username="cli",
    )
    execution = ExecutionContext(
        working_dir=settings.agents.working_dir,
        timeout_seconds=600,
        write_enabled=False,
        preview_only=False,
        live_workspace=settings.agents.working_dir,
    )

    class FakeRunnerResult:
        stdout = "done"
        stderr = ""
        exit_code = 0

    async def fake_run(**_: object) -> FakeRunnerResult:
        return FakeRunnerResult()

    with patch.object(workspace_manager, "snapshot") as snapshot_mock:
        with patch.object(adapter, "_read_output_file", return_value="done"):
            with patch.object(adapter, "_collect_json_logs", return_value=[]):
                with patch.object(runner, "run", side_effect=fake_run):
                    result = asyncio.run(adapter.run(request, execution))

    snapshot_mock.assert_not_called()
    assert result.status == ExecutionStatus.SUCCESS
    assert result.changes == []


def test_extract_final_message_prefers_last_agent_message() -> None:
    stdout = "\n".join(
        [
            '{"type":"thread.started","thread_id":"t1"}',
            '{"type":"item.completed","item":{"type":"agent_message","text":"first"}}',
            '{"type":"item.completed","item":{"type":"agent_message","text":"final"}}',
        ]
    )

    assert CodexCLIAdapter._extract_final_message(stdout) == "final"
