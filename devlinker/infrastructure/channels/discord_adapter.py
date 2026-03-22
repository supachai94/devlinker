"""Discord slash-command adapter for DevLinker."""

from __future__ import annotations

from time import monotonic
from typing import Optional

import discord
from discord import app_commands
from loguru import logger

from devlinker.application.service import DevLinkerService
from devlinker.domain.models import AgentPromptRequest
from devlinker.domain.ports import BaseChannelAdapter, BaseProgressReporter, BaseResponseFormatter
from devlinker.settings import DiscordSettings


class DiscordProgressReporter(BaseProgressReporter):
    """Edit the deferred interaction response with coarse-grained status updates."""

    def __init__(self, interaction: discord.Interaction, throttle_seconds: float) -> None:
        self._interaction = interaction
        self._throttle_seconds = throttle_seconds
        self._last_update_at = 0.0
        self._last_message = ""

    async def update(self, stage: str, message: str) -> None:
        del stage
        now = monotonic()
        if message == self._last_message and now - self._last_update_at < self._throttle_seconds:
            return

        self._last_message = message
        self._last_update_at = now
        try:
            await self._interaction.edit_original_response(content=f"⏳ {message}")
        except discord.HTTPException:
            logger.exception("Failed to update Discord progress message.")


class DevLinkerDiscordClient(discord.Client):
    """Concrete Discord client that registers slash commands during setup."""

    def __init__(self, adapter: "DiscordAdapter") -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(intents=intents)
        self.adapter = adapter
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        self.adapter.register_commands(self.tree)
        guild_object = self.adapter.guild_object
        if guild_object is not None:
            await self.tree.sync(guild=guild_object)
            logger.info("Synced Discord slash commands to guild {}", guild_object.id)
            return
        await self.tree.sync()
        logger.info("Synced Discord slash commands globally.")


class DiscordAdapter(BaseChannelAdapter):
    """Receive slash commands from Discord and send formatted responses back."""

    name = "discord"

    def __init__(
        self,
        settings: DiscordSettings,
        service: DevLinkerService,
        formatter: BaseResponseFormatter,
        default_agent: str,
    ) -> None:
        self._settings = settings
        self._service = service
        self._formatter = formatter
        self._default_agent = default_agent
        self._client = DevLinkerDiscordClient(self)

    @property
    def guild_object(self) -> Optional[discord.Object]:
        if self._settings.guild_id is None:
            return None
        return discord.Object(id=self._settings.guild_id)

    async def start(self) -> None:
        if not self._settings.token:
            raise ValueError("DISCORD_TOKEN is required to start the Discord adapter.")
        await self._client.start(self._settings.token)

    def register_commands(self, tree: app_commands.CommandTree) -> None:
        guild = self.guild_object

        @tree.command(
            name="forge",
            description="Run a prompt through the configured coding agent",
            guild=guild,
        )
        @app_commands.describe(
            prompt="Natural-language task for the agent",
            agent="Registered agent adapter name",
            auto_approve="Apply changes directly to the live workspace",
            dry_run="Generate a preview only",
        )
        async def forge(
            interaction: discord.Interaction,
            prompt: str,
            agent: Optional[str] = None,
            auto_approve: bool = False,
            dry_run: bool = False,
        ) -> None:
            request = AgentPromptRequest(
                prompt=prompt,
                source_channel="discord",
                user_id=interaction.user.id,
                username=str(interaction.user),
                role_ids=self._extract_role_ids(interaction),
                agent=agent or self._default_agent,
                auto_approve=auto_approve,
                dry_run=dry_run,
                metadata={"guild_id": str(interaction.guild_id or "")},
            )
            await self._execute_forge(interaction, request)

        @tree.command(
            name="approve",
            description="Apply a pending preview to the live workspace",
            guild=guild,
        )
        async def approve(interaction: discord.Interaction, request_id: str) -> None:
            await interaction.response.defer(thinking=True)
            reporter = DiscordProgressReporter(
                interaction,
                throttle_seconds=self._settings.progress_update_interval_seconds,
            )
            try:
                result = await self._service.approve(
                    request_id=request_id,
                    approver_id=interaction.user.id,
                    approver_name=str(interaction.user),
                    role_ids=self._extract_role_ids(interaction),
                    reporter=reporter,
                )
                payload = self._formatter.format_result(result)
            except Exception as exc:  # noqa: BLE001
                payload = self._formatter.format_error(exc, request_id)
            await self._send_messages(interaction, payload.messages)

        @tree.command(
            name="reject",
            description="Discard a pending preview",
            guild=guild,
        )
        async def reject(interaction: discord.Interaction, request_id: str) -> None:
            await interaction.response.defer(thinking=True)
            try:
                approval = await self._service.reject(
                    request_id=request_id,
                    actor_id=interaction.user.id,
                    role_ids=self._extract_role_ids(interaction),
                )
                payload = [
                    "\n".join(
                        [
                            "🟢 **Preview discarded**",
                            f"Request ID: `{approval.request_id}`",
                            "Preview workspace and approval token were removed.",
                        ]
                    )
                ]
            except Exception as exc:  # noqa: BLE001
                payload = self._formatter.format_error(exc, request_id).messages
            await self._send_messages(interaction, payload)

    async def _execute_forge(
        self,
        interaction: discord.Interaction,
        request: AgentPromptRequest,
    ) -> None:
        await interaction.response.defer(thinking=True)
        reporter = DiscordProgressReporter(
            interaction,
            throttle_seconds=self._settings.progress_update_interval_seconds,
        )
        try:
            result = await self._service.handle_forge(request, reporter)
            payload = self._formatter.format_result(result)
        except Exception as exc:  # noqa: BLE001
            payload = self._formatter.format_error(exc, request.request_id)
        await self._send_messages(interaction, payload.messages)

    async def _send_messages(self, interaction: discord.Interaction, messages: list[str]) -> None:
        if not messages:
            messages = ["No response generated."]

        first, *rest = messages
        await interaction.edit_original_response(content=first)
        for chunk in rest:
            await interaction.followup.send(chunk)

    @staticmethod
    def _extract_role_ids(interaction: discord.Interaction) -> list[int]:
        if isinstance(interaction.user, discord.Member):
            return [role.id for role in interaction.user.roles]
        return []
