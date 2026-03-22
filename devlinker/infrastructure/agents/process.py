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
            buffer = b""

            while True:
                payload = await stream.read(4096)
                if not payload:
                    break

                buffer += payload
                while True:
                    newline_index = buffer.find(b"\n")
                    if newline_index < 0:
                        break
                    line = buffer[:newline_index]
                    buffer = buffer[newline_index + 1 :]
                    if await self._handle_stream_line(line, sink, callback, process):
                        return

            if buffer:
                await self._handle_stream_line(buffer, sink, callback, process)

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

    async def _handle_stream_line(
        self,
        payload: bytes,
        sink: list[str],
        callback: Optional[LineCallback],
        process: asyncio.subprocess.Process,
    ) -> bool:
        text = payload.decode("utf-8", errors="replace").rstrip("\n")
        sink.append(text)

        if callback is None:
            return False

        try:
            await callback(text)
        except BaseException:  # noqa: BLE001
            if process.returncode is None:
                process.terminate()
            raise

        return False

    @staticmethod
    def _build_env(extra_env: Optional[Dict[str, str]]) -> Dict[str, str]:
        env = dict(os.environ)
        if extra_env:
            env.update(extra_env)
        return env
