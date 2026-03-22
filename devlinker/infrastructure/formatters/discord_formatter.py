"""Discord-friendly response rendering with chunk splitting."""

from __future__ import annotations

from typing import Iterable

from devlinker.domain.enums import ExecutionStatus
from devlinker.domain.models import AgentResult, FileChange, FormattedMessage
from devlinker.domain.ports import BaseResponseFormatter
from devlinker.settings import FormattingSettings


class DiscordFormatter(BaseResponseFormatter):
    """Format agent output into Discord-sized messages."""

    def __init__(self, settings: FormattingSettings) -> None:
        self._settings = settings

    def format_result(self, result: AgentResult) -> FormattedMessage:
        sections: list[str] = []
        icon = self._status_icon(result.status)
        sections.append(
            "\n".join(
                [
                    f"{icon} **DevLinker / {result.agent}**",
                    f"Request ID: `{result.request_id}`",
                    f"Summary: {result.summary}",
                    f"Duration: `{result.duration_seconds:.2f}s` | Exit code: `{result.exit_code}`",
                ]
            )
        )

        if result.approval_required and result.approval_request_id:
            sections.append(
                "\n".join(
                    [
                        "🟡 **Approval required**",
                        "การเปลี่ยนแปลงถูกสร้างใน preview workspace แล้ว แต่ยังไม่ได้ apply กับ live workspace",
                        f"ใช้ `/approve request_id:{result.approval_request_id}` เพื่อ apply จริง",
                        f"หรือ `/reject request_id:{result.approval_request_id}` เพื่อยกเลิก",
                    ]
                )
            )

        if result.final_answer.strip():
            sections.append(f"**Final answer**\n{result.final_answer.strip()}")

        if result.changes:
            sections.extend(self._format_changes(result.changes))

        if result.status != ExecutionStatus.SUCCESS and result.stderr.strip():
            sections.append(f"**stderr**\n```text\n{result.stderr[:self._settings.max_logs_chars]}\n```")

        if result.status != ExecutionStatus.SUCCESS and result.logs:
            joined_logs = "\n".join(result.logs[:10])
            sections.append(f"**Agent logs**\n```text\n{joined_logs[:self._settings.max_logs_chars]}\n```")

        return FormattedMessage(channel="discord", messages=self._split_sections(sections))

    def format_error(self, error: Exception, request_id: str) -> FormattedMessage:
        message = "\n".join(
            [
                "🔴 **DevLinker error**",
                f"Request ID: `{request_id}`",
                f"{type(error).__name__}: {error}",
            ]
        )
        return FormattedMessage(channel="discord", messages=self._split_sections([message]))

    def _format_changes(self, changes: Iterable[FileChange]) -> list[str]:
        sections = ["**Detected changes**"]
        for change in list(changes)[: self._settings.max_diff_files]:
            diff = change.diff or "Diff unavailable."
            clipped = diff[: self._settings.max_diff_chars_per_file]
            sections.append(
                "\n".join(
                    [
                        f"`{change.change_type.value}` `{change.path}`",
                        f"```diff\n{clipped}\n```",
                    ]
                )
            )
        return sections

    def _split_sections(self, sections: list[str]) -> list[str]:
        chunks: list[str] = []
        current = ""

        for section in sections:
            candidate = f"{current}\n\n{section}".strip() if current else section
            if len(candidate) <= self._settings.max_message_length:
                current = candidate
                continue

            if current:
                chunks.append(current)
            current = self._split_oversized_section(section)

            if len(current) <= self._settings.max_message_length:
                continue

            pieces = self._hard_split(current)
            chunks.extend(pieces[:-1])
            current = pieces[-1]

        if current:
            chunks.append(current)

        return chunks

    def _split_oversized_section(self, section: str) -> str:
        if len(section) <= self._settings.max_message_length:
            return section
        return "\n".join(line for line in section.splitlines())

    def _hard_split(self, text: str) -> list[str]:
        limit = self._settings.max_message_length
        parts: list[str] = []
        remaining = text
        while remaining:
            if len(remaining) <= limit:
                parts.append(remaining)
                break
            split_at = remaining.rfind("\n", 0, limit)
            if split_at <= 0:
                split_at = limit
            parts.append(remaining[:split_at].rstrip())
            remaining = remaining[split_at:].lstrip()
        return parts

    @staticmethod
    def _status_icon(status: ExecutionStatus) -> str:
        if status == ExecutionStatus.SUCCESS:
            return "🟢"
        if status == ExecutionStatus.BLOCKED:
            return "🟡"
        return "🔴"
