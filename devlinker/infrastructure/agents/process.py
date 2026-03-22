"""Async subprocess utilities used by external agent adapters."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Dict, Optional, Sequence

from devlinker.domain.errors import AgentExecutionError


LineCallback = Callable[[str], Awaitable[None]]


@dataclass
class ProcessExecutionResult:
    """Captured result from a subprocess invocation."""

    command: list[str]
    exit_code: int
    stdout: str
    stderr: str


class AsyncSubprocessRunner:
    """Run a subprocess while streaming stdout/stderr through async callbacks."""

    async def run(
        self,
        command: Sequence[str],
        cwd: Path,
        timeout_seconds: int,
        env: Optional[Dict[str, str]] = None,
        stdout_callback: Optional[LineCallback] = None,
        stderr_callback: Optional[LineCallback] = None,
    ) -> ProcessExecutionResult:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(cwd),
            env=self._build_env(env),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        callback_error: Optional[BaseException] = None

        async def consume(
            stream: asyncio.StreamReader,
            sink: list[str],
            callback: Optional[LineCallback],
        ) -> None:
            nonlocal callback_error

            while True:
                payload = await stream.readline()
                if not payload:
                    break

                text = payload.decode("utf-8", errors="replace").rstrip("\n")
                sink.append(text)

                if callback is None:
                    continue

                try:
                    await callback(text)
                except BaseException as exc:  # noqa: BLE001
                    callback_error = exc
                    if process.returncode is None:
                        process.terminate()
                    break

        stdout_task = asyncio.create_task(consume(process.stdout, stdout_lines, stdout_callback))
        stderr_task = asyncio.create_task(consume(process.stderr, stderr_lines, stderr_callback))
        wait_task = asyncio.create_task(process.wait())

        try:
            await asyncio.wait_for(
                asyncio.gather(stdout_task, stderr_task, wait_task),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.wait()
            raise AgentExecutionError(
                f"Agent command timed out after {timeout_seconds} seconds."
            ) from exc
        finally:
            for task in (stdout_task, stderr_task, wait_task):
                if not task.done():
                    task.cancel()

        if callback_error is not None:
            if isinstance(callback_error, BaseException):
                raise callback_error

        return ProcessExecutionResult(
            command=list(command),
            exit_code=process.returncode or 0,
            stdout="\n".join(stdout_lines).strip(),
            stderr="\n".join(stderr_lines).strip(),
        )

    @staticmethod
    def _build_env(extra_env: Optional[Dict[str, str]]) -> Dict[str, str]:
        env = dict(os.environ)
        if extra_env:
            env.update(extra_env)
        return env
