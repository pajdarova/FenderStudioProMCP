"""Tests for studio_one_mcp.ipc_bridge."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from studio_one_mcp.ipc_bridge import (
    IPCBridge,
    IPCError,
    IPCResponse,
    IPCTimeoutError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bridge(tmp_path: Path, poll_interval: float = 0.01) -> IPCBridge:
    return IPCBridge(ipc_dir=tmp_path, poll_interval=poll_interval)


async def _write_response_after(
    ipc_dir: Path, cmd_id: str, ok: bool, error: str | None, delay: float
) -> None:
    """Simulate the JS Extension writing a response file after a short delay."""
    await asyncio.sleep(delay)
    resp = {"id": cmd_id, "ok": ok, "error": error}
    (ipc_dir / f"resp-{cmd_id}.json").write_text(json.dumps(resp), encoding="utf-8")


# ---------------------------------------------------------------------------
# IPCBridge.dispatch — happy path
# ---------------------------------------------------------------------------

class TestIPCBridgeDispatch:
    @pytest.mark.asyncio
    async def test_writes_command_file(self, tmp_path: Path) -> None:
        bridge = _make_bridge(tmp_path)
        captured: list[dict] = []

        async def fake_wait(resp_file: Path, timeout: float) -> IPCResponse:
            # Read while the file still exists (deleted in finally after we return)
            for f in tmp_path.glob("cmd-*.json"):
                captured.append(json.loads(f.read_text()))
            return IPCResponse(id="x", ok=True, error=None)

        bridge._wait_for_response = fake_wait  # type: ignore[method-assign]
        await bridge.dispatch("Track", "Add Audio Track (mono)")

        assert len(captured) == 1
        assert captured[0]["category"] == "Track"
        assert captured[0]["name"] == "Add Audio Track (mono)"

    @pytest.mark.asyncio
    async def test_command_file_includes_args(self, tmp_path: Path) -> None:
        bridge = _make_bridge(tmp_path)
        captured: list[dict] = []

        async def fake_wait(resp_file: Path, timeout: float) -> IPCResponse:
            for f in tmp_path.glob("cmd-*.json"):
                captured.append(json.loads(f.read_text()))
            return IPCResponse(id="x", ok=True, error=None)

        bridge._wait_for_response = fake_wait  # type: ignore[method-assign]
        await bridge.dispatch("Track", "Cmd", args={"mode": "1", "cid": "{GUID}"})

        assert captured[0]["args"] == {"mode": "1", "cid": "{GUID}"}

    @pytest.mark.asyncio
    async def test_command_file_includes_transaction(self, tmp_path: Path) -> None:
        bridge = _make_bridge(tmp_path)
        captured: list[dict] = []

        async def fake_wait(resp_file: Path, timeout: float) -> IPCResponse:
            for f in tmp_path.glob("cmd-*.json"):
                captured.append(json.loads(f.read_text()))
            return IPCResponse(id="x", ok=True, error=None)

        bridge._wait_for_response = fake_wait  # type: ignore[method-assign]
        await bridge.dispatch("Edit", "Undo", transaction="My action")

        assert captured[0]["transaction"] == "My action"

    @pytest.mark.asyncio
    async def test_cleans_up_cmd_and_resp_files(self, tmp_path: Path) -> None:
        bridge = _make_bridge(tmp_path)

        # Simulate the JS Extension: write response and return it
        async def fake_wait(resp_file: Path, timeout: float) -> IPCResponse:
            resp_file.write_text(json.dumps({"id": "x", "ok": True, "error": None}))
            return IPCResponse(id="x", ok=True, error=None)

        bridge._wait_for_response = fake_wait  # type: ignore[method-assign]
        await bridge.dispatch("Track", "Cmd")

        assert list(tmp_path.glob("cmd-*.json")) == []
        assert list(tmp_path.glob("resp-*.json")) == []

    @pytest.mark.asyncio
    async def test_returns_ipc_response_on_success(self, tmp_path: Path) -> None:
        bridge = _make_bridge(tmp_path)

        async def fake_wait(resp_file: Path, timeout: float) -> IPCResponse:
            return IPCResponse(id="abc", ok=True, error=None)

        bridge._wait_for_response = fake_wait  # type: ignore[method-assign]
        resp = await bridge.dispatch("Track", "Cmd")

        assert resp.ok is True
        assert resp.error is None

    @pytest.mark.asyncio
    async def test_raises_ipc_error_on_failed_response(self, tmp_path: Path) -> None:
        bridge = _make_bridge(tmp_path)

        async def fake_wait(resp_file: Path, timeout: float) -> IPCResponse:
            return IPCResponse(id="abc", ok=False, error="command unknown")

        bridge._wait_for_response = fake_wait  # type: ignore[method-assign]

        with pytest.raises(IPCError, match="command unknown"):
            await bridge.dispatch("Bad", "Cmd")

    @pytest.mark.asyncio
    async def test_cleans_up_even_on_error(self, tmp_path: Path) -> None:
        bridge = _make_bridge(tmp_path)

        async def fake_wait(resp_file: Path, timeout: float) -> IPCResponse:
            return IPCResponse(id="x", ok=False, error="boom")

        bridge._wait_for_response = fake_wait  # type: ignore[method-assign]

        with pytest.raises(IPCError):
            await bridge.dispatch("Bad", "Cmd")

        assert list(tmp_path.glob("cmd-*.json")) == []


# ---------------------------------------------------------------------------
# _wait_for_response
# ---------------------------------------------------------------------------

class TestWaitForResponse:
    @pytest.mark.asyncio
    async def test_returns_when_file_appears(self, tmp_path: Path) -> None:
        bridge = _make_bridge(tmp_path)
        resp_file = tmp_path / "resp-test.json"

        asyncio.create_task(
            _write_response_after(tmp_path, "test", ok=True, error=None, delay=0.05)
        )

        resp = await bridge._wait_for_response(resp_file, timeout=2.0)
        assert resp.ok is True
        assert resp.id == "test"

    @pytest.mark.asyncio
    async def test_raises_timeout_when_no_file(self, tmp_path: Path) -> None:
        bridge = _make_bridge(tmp_path, poll_interval=0.01)
        resp_file = tmp_path / "resp-never.json"

        with pytest.raises(IPCTimeoutError, match="No response"):
            await bridge._wait_for_response(resp_file, timeout=0.1)

    @pytest.mark.asyncio
    async def test_retries_on_mid_write_json_error(self, tmp_path: Path) -> None:
        """If the response file exists but contains invalid JSON, keep polling."""
        bridge = _make_bridge(tmp_path, poll_interval=0.01)
        resp_file = tmp_path / "resp-x.json"

        # Write invalid JSON first, then valid JSON after a short delay
        resp_file.write_text("not json yet", encoding="utf-8")

        async def overwrite_later() -> None:
            await asyncio.sleep(0.05)
            resp_file.write_text(
                json.dumps({"id": "x", "ok": True, "error": None}), encoding="utf-8"
            )

        asyncio.create_task(overwrite_later())
        resp = await bridge._wait_for_response(resp_file, timeout=2.0)
        assert resp.ok is True

    @pytest.mark.asyncio
    async def test_creates_ipc_dir_if_missing(self, tmp_path: Path) -> None:
        ipc_dir = tmp_path / "deep" / "nested" / "ipc"
        bridge = IPCBridge(ipc_dir=ipc_dir, poll_interval=0.01)

        async def fake_wait(resp_file: Path, timeout: float) -> IPCResponse:
            return IPCResponse(id="x", ok=True, error=None)

        bridge._wait_for_response = fake_wait  # type: ignore[method-assign]
        await bridge.dispatch("Track", "Cmd")

        assert ipc_dir.exists()

    @pytest.mark.asyncio
    async def test_timeout_error_mentions_extension(self, tmp_path: Path) -> None:
        bridge = _make_bridge(tmp_path, poll_interval=0.01)
        resp_file = tmp_path / "resp-x.json"

        with pytest.raises(IPCTimeoutError) as exc_info:
            await bridge._wait_for_response(resp_file, timeout=0.05)

        assert "StudioOneMCPBridge" in str(exc_info.value)
