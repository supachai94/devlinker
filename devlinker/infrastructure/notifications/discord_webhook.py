"""Discord webhook sender for one-way notifications."""

from __future__ import annotations

from typing import Iterable, Optional

import aiohttp


class DiscordWebhookClient:
    """Send one or more message chunks to a Discord webhook."""

    def __init__(
        self,
        webhook_url: str,
        username: str = "DevLinker",
        avatar_url: Optional[str] = None,
    ) -> None:
        if not webhook_url:
            raise ValueError("DISCORD_WEBHOOK_URL is required to send webhook messages.")
        self._webhook_url = webhook_url
        self._username = username
        self._avatar_url = avatar_url

    async def send_messages(self, messages: Iterable[str]) -> None:
        async with aiohttp.ClientSession() as session:
            for message in messages:
                payload = {
                    "content": message,
                    "username": self._username,
                    "allowed_mentions": {"parse": []},
                }
                if self._avatar_url:
                    payload["avatar_url"] = self._avatar_url

                async with session.post(self._webhook_url, json=payload) as response:
                    if response.status >= 400:
                        body = await response.text()
                        raise RuntimeError(
                            f"Discord webhook request failed with status {response.status}: {body}"
                        )
