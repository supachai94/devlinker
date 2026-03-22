"""Configuration loading for DevLinker from YAML and environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

from devlinker.domain.enums import ApprovalMode, SandboxMode


def _parse_csv_integers(value: str) -> List[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def _parse_csv_strings(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class LoggingSettings(BaseModel):
    """Structured logging controls."""

    level: str = "INFO"
    json_logs: bool = False


class RateLimitSettings(BaseModel):
    """Simple in-memory rate limit configuration."""

    max_requests: int = 5
    per_seconds: int = 60


class DiscordSettings(BaseModel):
    """Discord-specific runtime settings."""

    token: str = ""
    webhook_url: str = ""
    guild_id: Optional[int] = None
    enable_plain_messages: bool = False
    allowed_user_ids: List[int] = Field(default_factory=list)
    allowed_role_ids: List[int] = Field(default_factory=list)
    allow_all_if_unconfigured: bool = False
    progress_update_interval_seconds: float = 1.5


class FormattingSettings(BaseModel):
    """Formatter-related thresholds."""

    max_message_length: int = 1900
    max_diff_files: int = 5
    max_diff_chars_per_file: int = 1400
    max_logs_chars: int = 1200


class SecuritySettings(BaseModel):
    """Controls around workspace and command safety."""

    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    blocked_command_patterns: List[str] = Field(
        default_factory=lambda: [
            r"\brm\s+-rf\b",
            r"\bmkfs\b",
            r"\bdd\s+if=",
            r"\bshutdown\b",
            r"\breboot\b",
            r"curl\s+.+\|\s*(?:bash|sh)",
            r">\s*/dev/(?:sd|disk)",
            r"chmod\s+-R\s+777\s+/",
        ]
    )
    allowed_command_prefixes: List[str] = Field(default_factory=list)
    max_file_bytes_for_diff: int = 200_000
    ignored_paths: List[str] = Field(
        default_factory=lambda: [
            ".git",
            ".venv",
            "__pycache__",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            ".devlinker",
        ]
    )
    approval_requires_same_user: bool = True


class CodexSettings(BaseModel):
    """Codex CLI adapter configuration."""

    command: str = "codex"
    model: Optional[str] = None
    write_sandbox: SandboxMode = SandboxMode.WORKSPACE_WRITE
    read_only_sandbox: SandboxMode = SandboxMode.READ_ONLY
    extra_args: List[str] = Field(default_factory=list)
    ephemeral: bool = True
    json_output: bool = True


class AgentSettings(BaseModel):
    """Cross-agent execution settings."""

    default_agent: str = "codex"
    working_dir: Path = Field(default_factory=lambda: Path("./workspace"))
    state_dir: Path = Field(default_factory=lambda: Path("./.devlinker/state"))
    preview_dir: Path = Field(default_factory=lambda: Path("./.devlinker/previews"))
    approval_mode: ApprovalMode = ApprovalMode.MANUAL
    timeout_seconds: int = 600
    dry_run: bool = False
    codex: CodexSettings = Field(default_factory=CodexSettings)

    @field_validator("working_dir", "state_dir", "preview_dir", mode="before")
    @classmethod
    def _coerce_path(cls, value: Any) -> Path:
        return Path(value)


class AppSettings(BaseModel):
    """Root configuration object used by the DI container."""

    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    discord: DiscordSettings = Field(default_factory=DiscordSettings)
    formatting: FormattingSettings = Field(default_factory=FormattingSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    agents: AgentSettings = Field(default_factory=AgentSettings)

    def prepare_runtime(self) -> None:
        """Create required runtime directories eagerly."""

        self.agents.working_dir.mkdir(parents=True, exist_ok=True)
        self.agents.state_dir.mkdir(parents=True, exist_ok=True)
        self.agents.preview_dir.mkdir(parents=True, exist_ok=True)


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    content = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(content, dict):
        raise ValueError("config.yaml must contain a top-level mapping")
    return content


def _load_env_overrides() -> Dict[str, Any]:
    env: Dict[str, Any] = {}

    if os.getenv("DISCORD_TOKEN"):
        env.setdefault("discord", {})["token"] = os.environ["DISCORD_TOKEN"]
    if os.getenv("DISCORD_WEBHOOK_URL"):
        env.setdefault("discord", {})["webhook_url"] = os.environ["DISCORD_WEBHOOK_URL"]
    if os.getenv("DISCORD_GUILD_ID"):
        env.setdefault("discord", {})["guild_id"] = int(os.environ["DISCORD_GUILD_ID"])
    if os.getenv("DISCORD_ENABLE_PLAIN_MESSAGES"):
        env.setdefault("discord", {})["enable_plain_messages"] = (
            os.environ["DISCORD_ENABLE_PLAIN_MESSAGES"].lower() == "true"
        )
    if os.getenv("DISCORD_ALLOWED_USER_IDS"):
        env.setdefault("discord", {})["allowed_user_ids"] = _parse_csv_integers(
            os.environ["DISCORD_ALLOWED_USER_IDS"]
        )
    if os.getenv("DISCORD_ALLOWED_ROLE_IDS"):
        env.setdefault("discord", {})["allowed_role_ids"] = _parse_csv_integers(
            os.environ["DISCORD_ALLOWED_ROLE_IDS"]
        )
    if os.getenv("DISCORD_ALLOW_ALL_IF_UNCONFIGURED"):
        env.setdefault("discord", {})["allow_all_if_unconfigured"] = (
            os.environ["DISCORD_ALLOW_ALL_IF_UNCONFIGURED"].lower() == "true"
        )

    if os.getenv("DEFAULT_AGENT"):
        env.setdefault("agents", {})["default_agent"] = os.environ["DEFAULT_AGENT"]
    if os.getenv("WORKING_DIR"):
        env.setdefault("agents", {})["working_dir"] = os.environ["WORKING_DIR"]
    if os.getenv("STATE_DIR"):
        env.setdefault("agents", {})["state_dir"] = os.environ["STATE_DIR"]
    if os.getenv("PREVIEW_DIR"):
        env.setdefault("agents", {})["preview_dir"] = os.environ["PREVIEW_DIR"]
    if os.getenv("APPROVAL_MODE"):
        env.setdefault("agents", {})["approval_mode"] = os.environ["APPROVAL_MODE"]
    if os.getenv("TIMEOUT_SECONDS"):
        env.setdefault("agents", {})["timeout_seconds"] = int(os.environ["TIMEOUT_SECONDS"])
    if os.getenv("DRY_RUN"):
        env.setdefault("agents", {})["dry_run"] = os.environ["DRY_RUN"].lower() == "true"

    if os.getenv("CODEX_COMMAND"):
        env.setdefault("agents", {}).setdefault("codex", {})["command"] = os.environ[
            "CODEX_COMMAND"
        ]
    if os.getenv("CODEX_MODEL"):
        env.setdefault("agents", {}).setdefault("codex", {})["model"] = os.environ["CODEX_MODEL"]
    if os.getenv("CODEX_WRITE_SANDBOX"):
        env.setdefault("agents", {}).setdefault("codex", {})["write_sandbox"] = os.environ[
            "CODEX_WRITE_SANDBOX"
        ]
    if os.getenv("CODEX_READ_ONLY_SANDBOX"):
        env.setdefault("agents", {}).setdefault("codex", {})["read_only_sandbox"] = os.environ[
            "CODEX_READ_ONLY_SANDBOX"
        ]
    if os.getenv("CODEX_EXTRA_ARGS"):
        env.setdefault("agents", {}).setdefault("codex", {})["extra_args"] = _parse_csv_strings(
            os.environ["CODEX_EXTRA_ARGS"]
        )

    if os.getenv("LOG_LEVEL"):
        env.setdefault("logging", {})["level"] = os.environ["LOG_LEVEL"]
    if os.getenv("JSON_LOGS"):
        env.setdefault("logging", {})["json_logs"] = os.environ["JSON_LOGS"].lower() == "true"

    if os.getenv("RATE_LIMIT_MAX_REQUESTS"):
        env.setdefault("security", {}).setdefault("rate_limit", {})["max_requests"] = int(
            os.environ["RATE_LIMIT_MAX_REQUESTS"]
        )
    if os.getenv("RATE_LIMIT_PER_SECONDS"):
        env.setdefault("security", {}).setdefault("rate_limit", {})["per_seconds"] = int(
            os.environ["RATE_LIMIT_PER_SECONDS"]
        )
    if os.getenv("BLOCKED_COMMAND_PATTERNS"):
        env.setdefault("security", {})["blocked_command_patterns"] = _parse_csv_strings(
            os.environ["BLOCKED_COMMAND_PATTERNS"]
        )
    if os.getenv("ALLOWED_COMMAND_PREFIXES"):
        env.setdefault("security", {})["allowed_command_prefixes"] = _parse_csv_strings(
            os.environ["ALLOWED_COMMAND_PREFIXES"]
        )

    return env


def load_settings(
    config_path: str = "config.yaml",
    env_file: str = ".env",
) -> AppSettings:
    """Load settings from config.yaml, then override with environment variables."""

    load_dotenv(dotenv_path=env_file, override=False)
    yaml_settings = _load_yaml(Path(config_path))
    merged = _deep_merge(yaml_settings, _load_env_overrides())
    settings = AppSettings.model_validate(merged)
    settings.prepare_runtime()
    return settings
