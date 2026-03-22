"""Tests for subprocess streaming helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from devlinker.infrastructure.agents.process import AsyncSubprocessRunner


@pytest.mark.asyncio
async def test_runner_handles_stdout_line_longer_than_asyncio_default_limit(tmp_path: Path) -> None:
    runner = AsyncSubprocessRunner()
    seen_lines: list[str] = []
    long_line = "x" * 80_000

    result = await runner.run(
        command=[
            sys.executable,
            "-c",
            (
                "import sys; "
                f"sys.stdout.write({long_line!r}); "
                "sys.stdout.flush()"
            ),
        ],
        cwd=tmp_path,
        timeout_seconds=10,
        stdout_callback=lambda line: _capture_line(seen_lines, line),
    )

    assert result.exit_code == 0
    assert result.stdout == long_line
    assert seen_lines == [long_line]


async def _capture_line(seen_lines: list[str], line: str) -> None:
    seen_lines.append(line)
