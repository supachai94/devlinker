"""Dependency wiring for DevLinker."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from devlinker.application.auth import AccessControlService
from devlinker.application.rate_limit import InMemoryRateLimiter
from devlinker.application.service import DevLinkerService
from devlinker.application.workspace import WorkspaceManager
from devlinker.domain.ports import BaseAgentAdapter, BaseChannelAdapter, BaseResponseFormatter
from devlinker.infrastructure.agents.codex_cli import CodexCLIAdapter
from devlinker.infrastructure.agents.process import AsyncSubprocessRunner
from devlinker.infrastructure.channels.discord_adapter import DiscordAdapter
from devlinker.infrastructure.formatters.discord_formatter import DiscordFormatter
from devlinker.infrastructure.formatters.text_formatter import TextFormatter
from devlinker.infrastructure.persistence.approval_store import FileApprovalStore
from devlinker.logging import configure_logging
from devlinker.settings import AppSettings, load_settings


@dataclass
class ServiceContainer:
    """Resolved runtime container."""

    settings: AppSettings
    service: DevLinkerService
    agent_adapters: Dict[str, BaseAgentAdapter]
    response_formatters: Dict[str, BaseResponseFormatter]
    channel_adapters: Dict[str, BaseChannelAdapter]


def build_container(settings: Optional[AppSettings] = None) -> ServiceContainer:
    """Create the runtime object graph."""

    resolved_settings = settings or load_settings()
    configure_logging(resolved_settings.logging)

    workspace_manager = WorkspaceManager(resolved_settings)
    approval_store = FileApprovalStore(resolved_settings.agents.state_dir / "pending_approvals.json")
    access_control = AccessControlService(resolved_settings.discord)
    rate_limiter = InMemoryRateLimiter(resolved_settings.security.rate_limit)

    agent_adapters: Dict[str, BaseAgentAdapter] = {
        "codex": CodexCLIAdapter(
            settings=resolved_settings,
            codex_settings=resolved_settings.agents.codex,
            runner=AsyncSubprocessRunner(),
            workspace_manager=workspace_manager,
        )
    }
    response_formatters: Dict[str, BaseResponseFormatter] = {
        "discord": DiscordFormatter(resolved_settings.formatting),
        "text": TextFormatter(),
    }
    service = DevLinkerService(
        settings=resolved_settings,
        agents=agent_adapters,
        access_control=access_control,
        rate_limiter=rate_limiter,
        workspace_manager=workspace_manager,
        approval_store=approval_store,
    )
    channel_adapters: Dict[str, BaseChannelAdapter] = {
        "discord": DiscordAdapter(
            settings=resolved_settings.discord,
            service=service,
            formatter=response_formatters["discord"],
            default_agent=resolved_settings.agents.default_agent,
        )
    }

    return ServiceContainer(
        settings=resolved_settings,
        service=service,
        agent_adapters=agent_adapters,
        response_formatters=response_formatters,
        channel_adapters=channel_adapters,
    )
