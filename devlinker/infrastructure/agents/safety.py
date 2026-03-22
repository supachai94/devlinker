"""Safety checks for streamed Codex JSON events."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, List

from devlinker.domain.errors import SafetyViolationError


class JsonCommandSafetyMonitor:
    """Inspect structured JSONL events and block dangerous shell commands."""

    _COMMAND_KEYS = {"command", "cmd", "raw_command", "tool_input", "input", "args"}

    def __init__(
        self,
        blocked_patterns: Iterable[str],
        allowed_prefixes: Iterable[str],
    ) -> None:
        self._blocked_patterns = [re.compile(pattern, flags=re.IGNORECASE) for pattern in blocked_patterns]
        self._allowed_prefixes = tuple(allowed_prefixes)

    def inspect_line(self, line: str) -> None:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return

        for candidate in self._extract_commands(payload):
            if self._is_explicitly_allowed(candidate):
                continue
            for pattern in self._blocked_patterns:
                if pattern.search(candidate):
                    raise SafetyViolationError(f"Blocked dangerous command: {candidate}")

    def _extract_commands(self, payload: Any) -> List[str]:
        commands: List[str] = []

        if isinstance(payload, dict):
            for key, value in payload.items():
                normalized = key.lower()
                if normalized in self._COMMAND_KEYS:
                    commands.extend(self._stringify(value))
                    continue
                commands.extend(self._extract_commands(value))
            return commands

        if isinstance(payload, list):
            for item in payload:
                commands.extend(self._extract_commands(item))

        return commands

    @staticmethod
    def _stringify(value: Any) -> List[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [" ".join(str(item) for item in value)]
        return []

    def _is_explicitly_allowed(self, command: str) -> bool:
        return bool(self._allowed_prefixes) and command.startswith(self._allowed_prefixes)
