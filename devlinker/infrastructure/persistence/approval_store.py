"""JSON-file persistence for pending approval requests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Dict, Optional

from devlinker.domain.models import PendingApproval
from devlinker.domain.ports import BaseApprovalStore


class FileApprovalStore(BaseApprovalStore):
    """Persist approval tokens to a JSON file under the runtime state directory."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    async def save(self, approval: PendingApproval) -> None:
        async with self._lock:
            payload = self._read_all()
            payload[approval.request_id] = approval.model_dump(mode="json")
            self._write_all(payload)

    async def get(self, request_id: str) -> Optional[PendingApproval]:
        async with self._lock:
            payload = self._read_all()
            data = payload.get(request_id)
            if data is None:
                return None
            return PendingApproval.model_validate(data)

    async def delete(self, request_id: str) -> Optional[PendingApproval]:
        async with self._lock:
            payload = self._read_all()
            data = payload.pop(request_id, None)
            if data is None:
                return None
            self._write_all(payload)
            return PendingApproval.model_validate(data)

    def _read_all(self) -> Dict[str, dict]:
        if not self._path.exists():
            return {}
        content = json.loads(self._path.read_text(encoding="utf-8") or "{}")
        if not isinstance(content, dict):
            return {}
        return content

    def _write_all(self, payload: Dict[str, dict]) -> None:
        temp_path = self._path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temp_path.replace(self._path)
