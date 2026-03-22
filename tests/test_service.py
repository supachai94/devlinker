"""Tests for manual approval flow in the orchestration layer."""

from __future__ import annotations

import pytest

from devlinker.application.auth import AccessControlService
from devlinker.application.rate_limit import InMemoryRateLimiter
from devlinker.application.service import DevLinkerService
from devlinker.application.workspace import WorkspaceManager
from devlinker.domain.models import AgentPromptRequest
from devlinker.infrastructure.persistence.approval_store import FileApprovalStore
from devlinker.settings import AppSettings
from tests.fakes import FakeAgentAdapter


@pytest.mark.asyncio
async def test_manual_mode_creates_preview_and_approval_record(tmp_path) -> None:
    working_dir = tmp_path / "workspace"
    working_dir.mkdir()
    settings = AppSettings.model_validate(
        {
            "discord": {
                "allow_all_if_unconfigured": True,
            },
            "agents": {
                "working_dir": str(working_dir),
                "state_dir": str(tmp_path / ".devlinker/state"),
                "preview_dir": str(tmp_path / ".devlinker/previews"),
                "approval_mode": "manual",
            },
        }
    )
    settings.prepare_runtime()
    workspace_manager = WorkspaceManager(settings)
    service = DevLinkerService(
        settings=settings,
        agents={"fake": FakeAgentAdapter()},
        access_control=AccessControlService(settings.discord),
        rate_limiter=InMemoryRateLimiter(settings.security.rate_limit),
        workspace_manager=workspace_manager,
        approval_store=FileApprovalStore(settings.agents.state_dir / "pending_approvals.json"),
    )

    result = await service.handle_forge(
        request=AgentPromptRequest(
            prompt="preview change",
            source_channel="discord",
            user_id=1,
            username="tester",
            role_ids=[],
            agent="fake",
            auto_approve=False,
            dry_run=False,
        ),
    )

    assert result.approval_required is True
    assert result.approval_request_id is not None
    assert not (working_dir / "result.txt").exists()
    assert result.preview_dir is not None
    assert (result.preview_dir / "result.txt").exists()


@pytest.mark.asyncio
async def test_approve_applies_changes_to_live_workspace(tmp_path) -> None:
    working_dir = tmp_path / "workspace"
    working_dir.mkdir()
    settings = AppSettings.model_validate(
        {
            "discord": {
                "allow_all_if_unconfigured": True,
            },
            "agents": {
                "working_dir": str(working_dir),
                "state_dir": str(tmp_path / ".devlinker/state"),
                "preview_dir": str(tmp_path / ".devlinker/previews"),
                "approval_mode": "manual",
            },
        }
    )
    settings.prepare_runtime()
    workspace_manager = WorkspaceManager(settings)
    store = FileApprovalStore(settings.agents.state_dir / "pending_approvals.json")
    service = DevLinkerService(
        settings=settings,
        agents={"fake": FakeAgentAdapter()},
        access_control=AccessControlService(settings.discord),
        rate_limiter=InMemoryRateLimiter(settings.security.rate_limit),
        workspace_manager=workspace_manager,
        approval_store=store,
    )

    preview = await service.handle_forge(
        request=AgentPromptRequest(
            prompt="apply change",
            source_channel="discord",
            user_id=1,
            username="tester",
            role_ids=[],
            agent="fake",
            auto_approve=False,
        ),
    )

    result = await service.approve(
        request_id=preview.request_id,
        approver_id=1,
        approver_name="tester",
        role_ids=[],
    )

    assert result.applied_changes is True
    assert (working_dir / "result.txt").read_text(encoding="utf-8") == "apply change"
