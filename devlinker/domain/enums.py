"""Enum definitions for request handling and execution flow."""

from __future__ import annotations

from enum import Enum


class ApprovalMode(str, Enum):
    """How DevLinker should treat write operations."""

    MANUAL = "manual"
    AUTO = "auto"
    NEVER = "never"


class SandboxMode(str, Enum):
    """Sandbox policy passed to the external agent."""

    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    DANGER_FULL_ACCESS = "danger-full-access"


class ExecutionStatus(str, Enum):
    """High-level outcome for an agent run."""

    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"


class ChangeType(str, Enum):
    """Supported file change kinds."""

    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
