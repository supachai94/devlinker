"""Test doubles shared across the test suite."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from devlinker.domain.enums import ExecutionStatus
from devlinker.domain.models import AgentPromptRequest, AgentResult, ExecutionContext
from devlinker.domain.ports import BaseAgentAdapter, BaseProgressReporter


class FakeAgentAdapter(BaseAgentAdapter):
    """Write a file into the target workspace and return a synthetic result."""

    name = "fake"

    async def run(
        self,
        request: AgentPromptRequest,
        execution: ExecutionContext,
        reporter: Optional[BaseProgressReporter] = None,
    ) -> AgentResult:
        if reporter:
            await reporter.update("fake", "Fake agent is writing files...")

        target = execution.working_dir / "result.txt"
        target.write_text(request.prompt, encoding="utf-8")

        return AgentResult(
            request_id=request.request_id,
            agent=self.name,
            status=ExecutionStatus.SUCCESS,
            summary="fake completed",
            final_answer="fake answer",
            stdout="",
            stderr="",
            exit_code=0,
            duration_seconds=0.1,
            working_dir=execution.working_dir,
            applied_changes=execution.write_enabled and not execution.preview_only,
            changes=[],
        )
