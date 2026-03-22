"""Tests for outbound Discord webhook delivery."""

from __future__ import annotations

import pytest

from devlinker.infrastructure.notifications.discord_webhook import DiscordWebhookClient


class _FakeResponse:
    def __init__(self, status: int = 204, body: str = "") -> None:
        self.status = status
        self._body = body

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def text(self) -> str:
        return self._body


class _FakeSession:
    def __init__(self, recorder: list[tuple[str, dict]]) -> None:
        self._recorder = recorder

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def post(self, url: str, json: dict) -> _FakeResponse:
        self._recorder.append((url, json))
        return _FakeResponse()


@pytest.mark.asyncio
async def test_discord_webhook_client_posts_each_message(monkeypatch) -> None:
    sent: list[tuple[str, dict]] = []

    monkeypatch.setattr(
        "devlinker.infrastructure.notifications.discord_webhook.aiohttp.ClientSession",
        lambda: _FakeSession(sent),
    )

    client = DiscordWebhookClient("https://example.com/webhook")
    await client.send_messages(["one", "two"])

    assert len(sent) == 2
    assert sent[0][1]["content"] == "one"
    assert sent[1][1]["content"] == "two"
