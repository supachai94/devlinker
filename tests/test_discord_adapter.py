"""Tests for Discord adapter helpers."""

from __future__ import annotations

from devlinker.infrastructure.channels.discord_adapter import DiscordAdapter


def test_normalize_message_prompt_strips_bot_mention() -> None:
    prompt = DiscordAdapter._normalize_message_prompt("<@12345> docker ps อยู่หน่อย", 12345)
    assert prompt == "docker ps อยู่หน่อย"


def test_normalize_message_prompt_keeps_plain_text() -> None:
    prompt = DiscordAdapter._normalize_message_prompt("docker ps อยู่หน่อย", 12345)
    assert prompt == "docker ps อยู่หน่อย"


def test_normalize_message_prompt_ignores_blank_messages() -> None:
    prompt = DiscordAdapter._normalize_message_prompt("   ", 12345)
    assert prompt == ""
