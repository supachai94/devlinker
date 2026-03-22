"""Authorization helpers for incoming channel requests."""

from __future__ import annotations

from devlinker.domain.errors import AuthorizationError
from devlinker.settings import DiscordSettings


class AccessControlService:
    """Validate user and role allowlists before a request is executed."""

    def __init__(self, settings: DiscordSettings) -> None:
        self._settings = settings

    def ensure_authorized(self, user_id: int, role_ids: list[int]) -> None:
        if self._settings.allow_all_if_unconfigured:
            return

        allowed_users = set(self._settings.allowed_user_ids)
        allowed_roles = set(self._settings.allowed_role_ids)

        if not allowed_users and not allowed_roles:
            raise AuthorizationError(
                "No Discord allowlist configured. Set DISCORD_ALLOWED_USER_IDS or DISCORD_ALLOWED_ROLE_IDS."
            )

        if user_id in allowed_users:
            return

        if allowed_roles.intersection(role_ids):
            return

        raise AuthorizationError("You are not allowed to invoke DevLinker.")
