"""Tests for Discord response chunking."""

from __future__ import annotations

from pathlib import Path

from devlinker.domain.enums import ChangeType, ExecutionStatus
from devlinker.domain.models import AgentResult, FileChange
from devlinker.infrastructure.formatters.discord_formatter import DiscordFormatter
from devlinker.settings import FormattingSettings


def test_formatter_splits_large_messages() -> None:
    formatter = DiscordFormatter(FormattingSettings(max_message_length=250))
    result = AgentResult(
        request_id="req-1",
        agent="codex",
        status=ExecutionStatus.SUCCESS,
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

    assert len(payload.messages) > 1
    assert all(len(message) <= 250 for message in payload.messages)
