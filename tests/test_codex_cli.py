"""Tests for Codex command construction."""

from __future__ import annotations

from pathlib import Path

from devlinker.application.workspace import WorkspaceManager
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


def test_extract_final_answer_prefers_last_agent_message() -> None:
    stdout = "\n".join(
        [
            '{"type":"thread.started","thread_id":"abc"}',
            '{"type":"item.completed","item":{"type":"agent_message","text":"progress"}}',
            '{"type":"item.completed","item":{"type":"agent_message","text":"final answer"}}',
        ]
    )

    assert CodexCLIAdapter._extract_final_answer(stdout) == "final answer"
