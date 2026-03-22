"""Pydantic models shared by the application and infrastructure layers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from devlinker.domain.enums import ChangeType, ExecutionStatus


class AgentPromptRequest(BaseModel):
    """Normalized request originating from a channel adapter."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    request_id: str = Field(default_factory=lambda: uuid4().hex)
    prompt: str
    source_channel: str
    user_id: int
    username: str
    role_ids: List[int] = Field(default_factory=list)
    agent: str = "codex"
    auto_approve: bool = False
    dry_run: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ExecutionContext(BaseModel):
    """Execution-specific metadata resolved by the orchestration layer."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    working_dir: Path
    timeout_seconds: int
    write_enabled: bool
    preview_only: bool = False
    live_workspace: Optional[Path] = None


class FileChange(BaseModel):
    """Textual representation of a workspace mutation."""

    path: str
    change_type: ChangeType
    diff: str


class PendingApproval(BaseModel):
    """Persisted approval record for manual apply mode."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    request_id: str
    prompt: str
    agent: str
    source_channel: str
    user_id: int
    username: str
    role_ids: List[int] = Field(default_factory=list)
    live_workspace: Path
    preview_workspace: Path
    created_at: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel):
    """Final outcome returned by an agent adapter."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    request_id: str
    agent: str
    status: ExecutionStatus
    original_prompt: str = ""
    summary: str
    final_answer: str
    stdout: str
    stderr: str
    logs: List[str] = Field(default_factory=list)
    exit_code: int = 0
    duration_seconds: float = 0.0
    working_dir: Path
    applied_changes: bool = False
    approval_required: bool = False
    approval_request_id: Optional[str] = None
    preview_dir: Optional[Path] = None
    changes: List[FileChange] = Field(default_factory=list)
    error_message: Optional[str] = None


class FormattedMessage(BaseModel):
    """Channel-ready message payload."""

    channel: str
    messages: List[str] = Field(default_factory=list)
