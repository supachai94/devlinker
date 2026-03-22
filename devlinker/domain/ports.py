"""Abstract ports used to isolate infrastructure implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from devlinker.domain.models import (
    AgentPromptRequest,
    AgentResult,
    ExecutionContext,
    FormattedMessage,
    PendingApproval,
)


class BaseProgressReporter(ABC):
    """Push progress updates back to the source channel."""

    @abstractmethod
    async def update(self, stage: str, message: str) -> None:
        """Publish a progress update."""


class BaseAgentAdapter(ABC):
    """Run prompts against an external coding agent."""

    name: str

    @abstractmethod
    async def run(
        self,
        request: AgentPromptRequest,
        execution: ExecutionContext,
        reporter: Optional[BaseProgressReporter] = None,
    ) -> AgentResult:
        """Execute a request and return the normalized result."""


class BaseResponseFormatter(ABC):
    """Render an agent result for a specific channel."""

    @abstractmethod
    def format_result(self, result: AgentResult) -> FormattedMessage:
        """Create a successful response payload."""

    @abstractmethod
    def format_error(self, error: Exception, request_id: str) -> FormattedMessage:
        """Create an error payload."""


class BaseChannelAdapter(ABC):
    """Receive requests and send responses on a transport."""

    name: str

    @abstractmethod
    async def start(self) -> None:
        """Start listening for incoming messages."""


class BaseApprovalStore(ABC):
    """Persistence contract for pending approval records."""

    @abstractmethod
    async def save(self, approval: PendingApproval) -> None:
        """Persist an approval record."""

    @abstractmethod
    async def get(self, request_id: str) -> Optional[PendingApproval]:
        """Fetch an approval record."""

    @abstractmethod
    async def delete(self, request_id: str) -> Optional[PendingApproval]:
        """Delete and return an approval record."""
