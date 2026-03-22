"""Discord adapter for slash commands and plain channel messages."""

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


class DiscordMessageProgressReporter(BaseProgressReporter):
    """Reply to a source message, then edit that reply with progress updates."""

    def __init__(self, message: discord.Message, throttle_seconds: float) -> None:
        self._message = message
        self._throttle_seconds = throttle_seconds
        self._last_update_at = 0.0
        self._last_message = ""
        self._reply: Optional[discord.Message] = None

    @property
    def reply_message(self) -> Optional[discord.Message]:
        return self._reply

    async def update(self, stage: str, message: str) -> None:
        del stage
        now = monotonic()
        if message == self._last_message and now - self._last_update_at < self._throttle_seconds:
            return

        self._last_message = message
        self._last_update_at = now
        try:
            if self._reply is None:
                self._reply = await self._message.reply(
                    f"⏳ {message}",
                    mention_author=False,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                return
            await self._reply.edit(content=f"⏳ {message}")
        except discord.HTTPException:
            logger.exception("Failed to update Discord message progress reply.")


class DevLinkerDiscordClient(discord.Client):
    """Concrete Discord client that registers slash commands during setup."""

    def __init__(self, adapter: "DiscordAdapter") -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        intents.messages = adapter.plain_messages_enabled
        intents.message_content = adapter.plain_messages_enabled
        super().__init__(intents=intents)
        self.adapter = adapter
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        self.adapter.register_commands(self.tree)
        guild_object = self.adapter.guild_object
        try:
            if guild_object is not None:
                await self.tree.sync(guild=guild_object)
                logger.info("Synced Discord slash commands to guild {}", guild_object.id)
                return
            await self.tree.sync()
            logger.info("Synced Discord slash commands globally.")
        except discord.Forbidden as exc:
            if guild_object is None:
                raise RuntimeError(
                    "Discord denied application command sync. Check the bot invite and token."
                ) from exc
            raise RuntimeError(
                "Discord denied access while syncing guild commands. "
                "Check that DISCORD_GUILD_ID matches a server where the bot is invited, "
                "and that the invite used both 'bot' and 'applications.commands' scopes."
            ) from exc
        except discord.NotFound as exc:
            if guild_object is None:
                raise
            raise RuntimeError(
                "DISCORD_GUILD_ID was not found. Copy the Server ID again from Discord Developer Mode."
            ) from exc

    async def on_message(self, message: discord.Message) -> None:
        await self.adapter.handle_message(message)


class DiscordAdapter(BaseChannelAdapter):
    """Receive slash commands and plain messages from Discord and send formatted responses back."""

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

    @property
    def plain_messages_enabled(self) -> bool:
        return self._settings.enable_plain_messages

    async def start(self) -> None:
        if not self._settings.token:
            raise ValueError("DISCORD_TOKEN is required to start the Discord adapter.")
        try:
            await self._client.start(self._settings.token)
        except discord.PrivilegedIntentsRequired as exc:
            if self.plain_messages_enabled:
                raise RuntimeError(
                    "Plain message mode is enabled, but Discord Message Content Intent is not "
                    "enabled in the Developer Portal. Enable 'Message Content Intent' in "
                    "Bot settings, or set DISCORD_ENABLE_PLAIN_MESSAGES=false to use slash "
                    "commands only."
                ) from exc
            raise
        except Exception:
            await self._client.close()
            raise

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

    async def handle_message(self, message: discord.Message) -> None:
        if not self.plain_messages_enabled:
            return

        if not self._should_process_message(message):
            return

        prompt = self._normalize_message_prompt(
            message.content,
            self._client.user.id if self._client.user is not None else None,
        )
        if not prompt:
            return

        request = AgentPromptRequest(
            prompt=prompt,
            source_channel="discord",
            user_id=message.author.id,
            username=str(message.author),
            role_ids=self._extract_role_ids_from_message(message),
            agent=self._default_agent,
            auto_approve=False,
            dry_run=False,
            metadata={
                "guild_id": str(message.guild.id if message.guild else ""),
                "channel_id": str(message.channel.id),
                "message_id": str(message.id),
            },
        )

        reporter = DiscordMessageProgressReporter(
            message,
            throttle_seconds=self._settings.progress_update_interval_seconds,
        )
        try:
            result = await self._service.handle_forge(request, reporter)
            payload = self._formatter.format_result(result)
        except Exception as exc:  # noqa: BLE001
            payload = self._formatter.format_error(exc, request.request_id)
        await self._send_message_replies(message, payload.messages, reporter.reply_message)

    async def _send_messages(self, interaction: discord.Interaction, messages: list[str]) -> None:
        if not messages:
            messages = ["No response generated."]

        first, *rest = messages
        await interaction.edit_original_response(content=first)
        for chunk in rest:
            await interaction.followup.send(chunk)

    async def _send_message_replies(
        self,
        source_message: discord.Message,
        messages: list[str],
        progress_reply: Optional[discord.Message],
    ) -> None:
        if not messages:
            messages = ["No response generated."]

        first, *rest = messages
        if progress_reply is not None:
            await progress_reply.edit(content=first)
        else:
            await source_message.reply(
                first,
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )

        for chunk in rest:
            await source_message.reply(
                chunk,
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )

    @staticmethod
    def _normalize_message_prompt(raw_content: str, bot_user_id: Optional[int]) -> str:
        prompt = raw_content.strip()
        if not prompt:
            return ""

        if bot_user_id is None:
            return prompt

        for mention in (f"<@{bot_user_id}>", f"<@!{bot_user_id}>"):
            if prompt.startswith(mention):
                prompt = prompt[len(mention) :].strip()

        return prompt

    @staticmethod
    def _should_process_message(message: discord.Message) -> bool:
        if message.author.bot:
            return False
        if message.guild is None:
            return False
        if not message.content.strip():
            return False
        return True

    @staticmethod
    def _extract_role_ids(interaction: discord.Interaction) -> list[int]:
        if isinstance(interaction.user, discord.Member):
            return [role.id for role in interaction.user.roles]
        return []

    @staticmethod
    def _extract_role_ids_from_message(message: discord.Message) -> list[int]:
        if isinstance(message.author, discord.Member):
            return [role.id for role in message.author.roles]
        return []
