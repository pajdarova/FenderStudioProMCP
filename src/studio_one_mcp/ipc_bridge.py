"""Python-side IPC bridge for the StudioOneMCPBridge JS Extension.

Write workflow:
  1. Python writes ~/Documents/StudioOneMCP/ipc/cmd-{uuid}.json
  2. The JS Extension (polling every 100 ms) picks it up, calls
     Host.GUI.Commands.interpretCommand, and writes resp-{uuid}.json.
  3. Python polls for resp-{uuid}.json with configurable timeout.
  4. Both files are cleaned up regardless of outcome.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from pathlib import Path


class IPCError(Exception):
    """Extension returned an error response."""


class IPCTimeoutError(IPCError):
    """No response arrived within the timeout."""


@dataclass
class IPCResponse:
    id: str
    ok: bool
    error: str | None


def _default_ipc_dir() -> Path:
    return Path.home() / "Documents" / "StudioOneMCP" / "ipc"


class IPCBridge:
    """Async bridge to the StudioOneMCPBridge Studio One JS Extension.

    Parameters
    ----------
    ipc_dir:
        Override the IPC directory (default: ~/Documents/StudioOneMCP/ipc/).
    poll_interval:
        Seconds between response-file polls (default 0.05 = 50 ms).
    """

    def __init__(
        self,
        ipc_dir: Path | None = None,
        poll_interval: float = 0.05,
    ) -> None:
        self._dir = ipc_dir or _default_ipc_dir()
        self._poll = poll_interval

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def dispatch(
        self,
        category: str,
        name: str,
        args: dict[str, str] | None = None,
        transaction: str | None = None,
        timeout: float = 5.0,
    ) -> IPCResponse:
        """Dispatch a Studio One command via the Extension IPC bridge.

        Parameters
        ----------
        category:
            Studio One command category (e.g. "Track", "Edit", "Audio").
        name:
            Command name within the category.
        args:
            Optional key-value command arguments (both str).
        transaction:
            If set, wraps the command in beginTransaction/endTransaction.
        timeout:
            Seconds to wait for the Extension to respond.

        Raises
        ------
        IPCTimeoutError
            No response within *timeout* seconds (Extension not running?).
        IPCError
            Extension reported a command error.
        """
        self._dir.mkdir(parents=True, exist_ok=True)

        cmd_id = str(uuid.uuid4())
        payload: dict[str, object] = {
            "id": cmd_id,
            "category": category,
            "name": name,
        }
        if args:
            payload["args"] = args
        if transaction:
            payload["transaction"] = transaction

        cmd_file = self._dir / f"cmd-{cmd_id}.json"
        resp_file = self._dir / f"resp-{cmd_id}.json"

        try:
            cmd_file.write_text(json.dumps(payload), encoding="utf-8")
            resp = await self._wait_for_response(resp_file, timeout)
        finally:
            cmd_file.unlink(missing_ok=True)
            resp_file.unlink(missing_ok=True)

        if not resp.ok:
            raise IPCError(
                f"Studio One command '{category}/{name}' failed: {resp.error}"
            )
        return resp

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _wait_for_response(self, resp_file: Path, timeout: float) -> IPCResponse:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout

        while loop.time() < deadline:
            if resp_file.exists():
                try:
                    data = json.loads(resp_file.read_text(encoding="utf-8"))
                    return IPCResponse(
                        id=data.get("id", ""),
                        ok=bool(data.get("ok", False)),
                        error=data.get("error"),
                    )
                except (json.JSONDecodeError, OSError):
                    pass  # mid-write race; retry on next tick
            await asyncio.sleep(self._poll)

        raise IPCTimeoutError(
            f"No response from Studio One after {timeout}s. "
            "Make sure Studio One is running and the StudioOneMCPBridge "
            "extension is installed (run install_ipc_extension first)."
        )
