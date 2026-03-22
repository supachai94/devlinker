"""Tests for Discord response chunking."""

from __future__ import annotations

from pathlib import Path

from devlinker.domain.enums import ChangeType, ExecutionStatus
from devlinker.domain.models import AgentResult, FileChange
from devlinker.infrastructure.formatters.discord_formatter import DiscordFormatter
from devlinker.settings import FormattingSettings


def test_formatter_prefers_single_message_for_large_success_output() -> None:
    formatter = DiscordFormatter(FormattingSettings(max_message_length=250))
    result = AgentResult(
        request_id="req-1",
        agent="codex",
        status=ExecutionStatus.SUCCESS,
        original_prompt="large prompt",
        summary="done",
        final_answer="A" * 500,
        stdout="",
        stderr="",
        logs=[],
        exit_code=0,
        duration_seconds=1.2,
        working_dir=Path("."),
        changes=[
            FileChange(
                path="sample.py",
                change_type=ChangeType.MODIFIED,
                diff="@@\n-" + ("x" * 200) + "\n+" + ("y" * 200),
            )
        ],
    )

    payload = formatter.format_result(result)

    assert len(payload.messages) == 1
    assert len(payload.messages[0]) <= 250
    assert payload.messages[0].endswith("...") or "truncated to fit one Discord message" in payload.messages[0]
    assert "Diff omitted to keep a single Discord message." in payload.messages[0]


def test_formatter_includes_original_prompt() -> None:
    formatter = DiscordFormatter(FormattingSettings())
    result = AgentResult(
        request_id="req-2",
        agent="codex",
        status=ExecutionStatus.SUCCESS,
        original_prompt="ลอง docker ps ดูหน่อย",
        summary="done",
        final_answer="มี 20 containers",
        stdout="",
        stderr="",
        logs=[],
        exit_code=0,
        duration_seconds=0.8,
        working_dir=Path("."),
    )

    payload = formatter.format_result(result)
    joined = "\n".join(payload.messages)

    assert "**Prompt**" in joined
    assert "ลอง docker ps ดูหน่อย" in joined
    assert "มี 20 containers" in joined
    assert "Request ID:" not in joined


def test_formatter_falls_back_to_split_for_failed_results() -> None:
    formatter = DiscordFormatter(FormattingSettings(max_message_length=180))
    result = AgentResult(
        request_id="req-3",
        agent="codex",
        status=ExecutionStatus.FAILED,
        original_prompt="broken",
        summary="failed",
        final_answer="",
        stdout="",
        stderr="E" * 400,
        logs=["log line 1", "log line 2"],
        exit_code=1,
        duration_seconds=1.0,
        working_dir=Path("."),
    )

    payload = formatter.format_result(result)

    assert len(payload.messages) > 1
    assert any("**stderr**" in message for message in payload.messages)
