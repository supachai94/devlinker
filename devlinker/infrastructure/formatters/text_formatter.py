"""Plain-text response rendering for CLI and logs."""

from __future__ import annotations

from devlinker.domain.models import AgentResult, FormattedMessage
from devlinker.domain.ports import BaseResponseFormatter


class TextFormatter(BaseResponseFormatter):
    """Simple text formatter for local one-shot execution."""

    def format_result(self, result: AgentResult) -> FormattedMessage:
        lines = [
            f"[{result.status.value}] {result.summary}",
            f"request_id={result.request_id} agent={result.agent} duration={result.duration_seconds:.2f}s",
            "",
            result.final_answer.strip() or "(no final answer)",
        ]

        if result.changes:
            lines.extend(["", "Detected changes:"])
            for change in result.changes:
                lines.append(f"- {change.change_type.value}: {change.path}")

        return FormattedMessage(channel="text", messages=["\n".join(lines).strip()])

    def format_error(self, error: Exception, request_id: str) -> FormattedMessage:
        return FormattedMessage(
            channel="text",
            messages=[f"[error] request_id={request_id} {type(error).__name__}: {error}"],
        )
