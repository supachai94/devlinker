"""Codex CLI adapter implementation."""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter
from typing import Optional

from loguru import logger

from devlinker.application.workspace import WorkspaceManager
from devlinker.domain.enums import ExecutionStatus
from devlinker.domain.models import AgentPromptRequest, AgentResult, ExecutionContext
from devlinker.domain.ports import BaseAgentAdapter, BaseProgressReporter
from devlinker.infrastructure.agents.process import AsyncSubprocessRunner
from devlinker.infrastructure.agents.safety import JsonCommandSafetyMonitor
from devlinker.settings import AppSettings, CodexSettings


class CodexCLIAdapter(BaseAgentAdapter):
    """Run prompts through `codex exec` and normalize the resulting output."""

    name = "codex"

    def __init__(
        self,
        settings: AppSettings,
        codex_settings: CodexSettings,
        runner: AsyncSubprocessRunner,
        workspace_manager: WorkspaceManager,
    ) -> None:
        self._settings = settings
        self._codex_settings = codex_settings
        self._runner = runner
        self._workspace_manager = workspace_manager

    async def run(
        self,
        request: AgentPromptRequest,
        execution: ExecutionContext,
        reporter: Optional[BaseProgressReporter] = None,
    ) -> AgentResult:
        start = perf_counter()
        before_snapshot = self._workspace_manager.snapshot(execution.working_dir)
        output_file = self._settings.agents.state_dir / f"{request.request_id}-last-message.txt"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        if output_file.exists():
            output_file.unlink()
        monitor = JsonCommandSafetyMonitor(
            blocked_patterns=self._settings.security.blocked_command_patterns,
            allowed_prefixes=self._settings.security.allowed_command_prefixes,
        )

        if reporter:
            await reporter.update("dispatch", "กำลังส่ง prompt ไป Codex...")

        command = self.build_command(request, execution, output_file)
        logger.info("Executing Codex command: {}", command)

        async def on_stdout(line: str) -> None:
            monitor.inspect_line(line)

        result = await self._runner.run(
            command=command,
            cwd=execution.working_dir,
            timeout_seconds=execution.timeout_seconds,
            stdout_callback=on_stdout,
        )

        after_snapshot = self._workspace_manager.snapshot(execution.working_dir)
        changes = self._workspace_manager.diff_snapshots(before_snapshot, after_snapshot)
        final_answer = self._read_output_file(output_file, fallback=result.stdout)
        logs = self._collect_json_logs(result.stdout)
        summary = self._build_summary(final_answer, changes, execution.preview_only)

        if reporter:
            await reporter.update("formatting", "กำลังสรุปผลลัพธ์และตรวจ diff...")

        status = ExecutionStatus.SUCCESS if result.exit_code == 0 else ExecutionStatus.FAILED
        duration = perf_counter() - start

        return AgentResult(
            request_id=request.request_id,
            agent=self.name,
            status=status,
            summary=summary,
            final_answer=final_answer,
            stdout=result.stdout,
            stderr=result.stderr,
            logs=logs,
            exit_code=result.exit_code,
            duration_seconds=duration,
            working_dir=execution.working_dir,
            applied_changes=execution.write_enabled and not execution.preview_only and result.exit_code == 0,
            changes=changes,
            error_message=result.stderr or None,
        )

    def build_command(
        self,
        request: AgentPromptRequest,
        execution: ExecutionContext,
        output_file: Path,
    ) -> list[str]:
        command = [
            self._codex_settings.command,
            "exec",
            "--skip-git-repo-check",
            "--color",
            "never",
            "--output-last-message",
            str(output_file),
            "--cd",
            str(execution.working_dir),
            "--sandbox",
            self._resolve_sandbox(execution),
        ]

        if self._codex_settings.json_output:
            command.append("--json")

        if self._codex_settings.ephemeral:
            command.append("--ephemeral")

        if self._codex_settings.model:
            command.extend(["--model", self._codex_settings.model])

        command.extend(self._codex_settings.extra_args)
        command.append(request.prompt)
        return command

    def _resolve_sandbox(self, execution: ExecutionContext) -> str:
        if execution.write_enabled:
            return self._codex_settings.write_sandbox.value
        return self._codex_settings.read_only_sandbox.value

    @staticmethod
    def _read_output_file(output_file: Path, fallback: str) -> str:
        if output_file.exists():
            content = output_file.read_text(encoding="utf-8", errors="replace").strip()
            if content:
                return content
        return fallback.strip()

    @staticmethod
    def _collect_json_logs(stdout: str) -> list[str]:
        logs: list[str] = []
        for line in stdout.splitlines():
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                if line.strip():
                    logs.append(line.strip())
                continue

            event_type = payload.get("type", "event")
            message = CodexCLIAdapter._extract_text(payload)
            if message:
                logs.append(f"{event_type}: {message}")
            else:
                logs.append(f"{event_type}: {json.dumps(payload, ensure_ascii=False)}")
        return logs

    @staticmethod
    def _extract_text(payload: object) -> str:
        if isinstance(payload, dict):
            for key in ("message", "content", "text", "output"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            for value in payload.values():
                extracted = CodexCLIAdapter._extract_text(value)
                if extracted:
                    return extracted
        if isinstance(payload, list):
            fragments = [CodexCLIAdapter._extract_text(item) for item in payload]
            return " ".join(fragment for fragment in fragments if fragment).strip()
        return ""

    @staticmethod
    def _build_summary(final_answer: str, changes: list, preview_only: bool) -> str:
        first_line = final_answer.strip().splitlines()[0] if final_answer.strip() else ""
        if first_line:
            return first_line[:180]

        change_count = len(changes)
        if preview_only:
            return f"Preview completed with {change_count} detected file change(s)."
        return f"Execution completed with {change_count} detected file change(s)."
