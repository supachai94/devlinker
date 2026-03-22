"""Main orchestration service for forge, approve, and reject flows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from loguru import logger

from devlinker.application.auth import AccessControlService
from devlinker.application.rate_limit import InMemoryRateLimiter
from devlinker.application.workspace import WorkspaceManager
from devlinker.domain.enums import ApprovalMode
from devlinker.domain.errors import PendingApprovalNotFoundError
from devlinker.domain.models import AgentPromptRequest, AgentResult, ExecutionContext, PendingApproval
from devlinker.domain.ports import BaseAgentAdapter, BaseApprovalStore, BaseProgressReporter
from devlinker.settings import AppSettings


class DevLinkerService:
    """Coordinate authorization, rate limits, approvals, and agent execution."""

    def __init__(
        self,
        settings: AppSettings,
        agents: Dict[str, BaseAgentAdapter],
        access_control: AccessControlService,
        rate_limiter: InMemoryRateLimiter,
        workspace_manager: WorkspaceManager,
        approval_store: BaseApprovalStore,
    ) -> None:
        self._settings = settings
        self._agents = agents
        self._access_control = access_control
        self._rate_limiter = rate_limiter
        self._workspace_manager = workspace_manager
        self._approval_store = approval_store

    async def handle_forge(
        self,
        request: AgentPromptRequest,
        reporter: Optional[BaseProgressReporter] = None,
    ) -> AgentResult:
        if reporter:
            await reporter.update("authorizing", "กำลังตรวจสอบสิทธิ์และ rate limit...")

        if request.source_channel != "cli":
            self._access_control.ensure_authorized(request.user_id, request.role_ids)
            self._rate_limiter.check(request.user_id)

        agent = self._resolve_agent(request.agent)
        live_workspace = self._workspace_manager.ensure_live_workspace()
        preview_mode = self._should_use_preview(request)
        execution_workspace = live_workspace

        if preview_mode:
            execution_workspace = self._workspace_manager.clone_for_preview(request.request_id)
            if reporter:
                await reporter.update("preview", "สร้าง preview workspace สำหรับตรวจสอบการแก้ไข...")

        execution = ExecutionContext(
            working_dir=execution_workspace,
            timeout_seconds=self._settings.agents.timeout_seconds,
            write_enabled=True if preview_mode else self._should_apply_live_changes(request),
            preview_only=preview_mode,
            live_workspace=live_workspace,
        )

        logger.info(
            "Running request {} via agent={} preview_only={} live_workspace={}",
            request.request_id,
            request.agent,
            preview_mode,
            live_workspace,
        )

        try:
            result = await agent.run(request, execution, reporter)
        except Exception:
            if preview_mode:
                self._workspace_manager.cleanup_preview(request.request_id)
            raise

        if preview_mode:
            result.applied_changes = False
            result.preview_dir = execution_workspace
            approval_required = (
                self._settings.agents.approval_mode == ApprovalMode.MANUAL
                and not request.dry_run
                and not request.auto_approve
            )
            result.approval_required = approval_required
            result.approval_request_id = request.request_id if approval_required else None
            if approval_required:
                await self._approval_store.save(
                    PendingApproval(
                        request_id=request.request_id,
                        prompt=request.prompt,
                        agent=request.agent,
                        source_channel=request.source_channel,
                        user_id=request.user_id,
                        username=request.username,
                        role_ids=request.role_ids,
                        live_workspace=live_workspace,
                        preview_workspace=execution_workspace,
                        created_at=datetime.now(timezone.utc).isoformat(),
                        metadata=request.metadata,
                    )
                )
            else:
                self._workspace_manager.cleanup_preview(request.request_id)

        return result

    async def approve(
        self,
        request_id: str,
        approver_id: int,
        approver_name: str,
        role_ids: list[int],
        reporter: Optional[BaseProgressReporter] = None,
    ) -> AgentResult:
        self._access_control.ensure_authorized(approver_id, role_ids)
        self._rate_limiter.check(approver_id)

        approval = await self._approval_store.get(request_id)
        if approval is None:
            raise PendingApprovalNotFoundError(f"Approval request '{request_id}' was not found.")

        if (
            self._settings.security.approval_requires_same_user
            and approval.user_id != approver_id
        ):
            raise PendingApprovalNotFoundError(
                "Approval token exists but cannot be used by a different user."
            )

        if reporter:
            await reporter.update("approval", "อนุมัติแล้ว กำลังรันกับ live workspace...")

        request = AgentPromptRequest(
            request_id=request_id,
            prompt=approval.prompt,
            source_channel=approval.source_channel,
            user_id=approver_id,
            username=approver_name,
            role_ids=role_ids,
            agent=approval.agent,
            auto_approve=True,
            metadata=approval.metadata,
        )

        agent = self._resolve_agent(approval.agent)
        execution = ExecutionContext(
            working_dir=approval.live_workspace,
            timeout_seconds=self._settings.agents.timeout_seconds,
            write_enabled=True,
            preview_only=False,
            live_workspace=approval.live_workspace,
        )

        try:
            result = await agent.run(request, execution, reporter)
        finally:
            await self._approval_store.delete(request_id)
            self._workspace_manager.cleanup_preview(request_id)

        return result

    async def reject(
        self,
        request_id: str,
        actor_id: int,
        role_ids: list[int],
    ) -> PendingApproval:
        self._access_control.ensure_authorized(actor_id, role_ids)
        self._rate_limiter.check(actor_id)

        approval = await self._approval_store.get(request_id)
        if approval is None:
            raise PendingApprovalNotFoundError(f"Approval request '{request_id}' was not found.")

        if (
            self._settings.security.approval_requires_same_user
            and approval.user_id != actor_id
        ):
            raise PendingApprovalNotFoundError(
                "Approval token exists but cannot be rejected by a different user."
            )

        await self._approval_store.delete(request_id)
        self._workspace_manager.cleanup_preview(request_id)
        return approval

    def _resolve_agent(self, agent_name: str) -> BaseAgentAdapter:
        try:
            return self._agents[agent_name]
        except KeyError as exc:
            available = ", ".join(sorted(self._agents))
            raise ValueError(f"Unknown agent '{agent_name}'. Available agents: {available}.") from exc

    def _should_apply_live_changes(self, request: AgentPromptRequest) -> bool:
        if self._settings.agents.approval_mode == ApprovalMode.NEVER:
            return False

        if request.dry_run:
            return False

        if self._settings.agents.approval_mode == ApprovalMode.AUTO:
            return True

        return request.auto_approve

    def _should_use_preview(self, request: AgentPromptRequest) -> bool:
        if request.dry_run:
            return True

        if self._settings.agents.approval_mode == ApprovalMode.NEVER:
            return True

        if self._settings.agents.approval_mode == ApprovalMode.MANUAL and not request.auto_approve:
            return True

        return False
