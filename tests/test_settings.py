"""Tests for settings loading and env override behavior."""

from __future__ import annotations

from pathlib import Path

from devlinker.settings import load_settings


def test_load_settings_prefers_environment_over_yaml(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
discord:
  token: from-yaml
agents:
  default_agent: codex
  working_dir: ./workspace-yaml
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("DISCORD_TOKEN", "from-env")
    monkeypatch.setenv("WORKING_DIR", str(tmp_path / "workspace-env"))

    settings = load_settings(config_path=str(config_path), env_file=str(tmp_path / ".env"))

    assert settings.discord.token == "from-env"
    assert settings.agents.working_dir == Path(tmp_path / "workspace-env")
