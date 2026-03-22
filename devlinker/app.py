"""CLI entrypoints for running DevLinker."""

from __future__ import annotations

import argparse
import asyncio

from devlinker.bootstrap import build_container
from devlinker.domain.models import AgentPromptRequest
from devlinker.infrastructure.notifications.discord_webhook import DiscordWebhookClient


async def run_bot() -> None:
    """Start the Discord adapter."""

    container = build_container()
    await container.channel_adapters["discord"].start()


async def run_once(
    prompt: str,
    agent: str,
    auto_approve: bool,
    dry_run: bool,
    send_webhook: bool,
) -> None:
    """Execute a single request without a channel adapter."""

    container = build_container()
    request = AgentPromptRequest(
        prompt=prompt,
        source_channel="cli",
        user_id=0,
        username="cli",
        role_ids=[],
        agent=agent or container.settings.agents.default_agent,
        auto_approve=auto_approve,
        dry_run=dry_run,
    )

    formatter_name = "discord" if send_webhook else "text"
    formatter = container.response_formatters[formatter_name]

    try:
        result = await container.service.handle_forge(request)
        messages = formatter.format_result(result).messages
    except Exception as exc:  # noqa: BLE001
        messages = formatter.format_error(exc, request.request_id).messages

    if send_webhook:
        webhook = DiscordWebhookClient(container.settings.discord.webhook_url)
        await webhook.send_messages(messages)
        print(f"Sent {len(messages)} message(s) to Discord webhook.")
        return

    for message in messages:
        print(message)


async def webhook_test(message: str) -> None:
    """Send a direct test notification to the configured Discord webhook."""

    container = build_container()
    webhook = DiscordWebhookClient(container.settings.discord.webhook_url)
    await webhook.send_messages([message])
    print("Discord webhook test message sent.")


def main() -> None:
    """Parse arguments and dispatch to the selected command."""

    parser = argparse.ArgumentParser(prog="devlinker")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bot_parser = subparsers.add_parser("bot", help="Start the Discord bot")
    bot_parser.set_defaults(handler=lambda args: run_bot())

    once_parser = subparsers.add_parser("run-once", help="Execute a single prompt locally")
    once_parser.add_argument("--prompt", required=True, help="Prompt to send to the agent")
    once_parser.add_argument("--agent", default="codex", help="Agent adapter name")
    once_parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Apply changes directly to the live workspace",
    )
    once_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Create only a preview workspace",
    )
    once_parser.add_argument(
        "--send-webhook",
        action="store_true",
        help="Send the formatted result to DISCORD_WEBHOOK_URL instead of stdout",
    )
    once_parser.set_defaults(
        handler=lambda args: run_once(
            prompt=args.prompt,
            agent=args.agent,
            auto_approve=args.auto_approve,
            dry_run=args.dry_run,
            send_webhook=args.send_webhook,
        )
    )

    webhook_parser = subparsers.add_parser(
        "webhook-test",
        help="Send a test message to the configured Discord webhook",
    )
    webhook_parser.add_argument(
        "--message",
        default="DevLinker webhook test: configuration is working.",
        help="Message to send to DISCORD_WEBHOOK_URL",
    )
    webhook_parser.set_defaults(handler=lambda args: webhook_test(args.message))

    args = parser.parse_args()
    asyncio.run(args.handler(args))
