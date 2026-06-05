"""Tests for deferring the client warm-up until after the MCP handshake.

These are network-free: the warm-up worker is stubbed so no Label Studio SDK
import or HTTP call happens.
"""

import asyncio
import threading

import pytest
from mcp import types

import label_studio_mcp.main as main


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    """Reset the run-once guard and stub the heavy warm-up worker."""
    main._warm_up_started.clear()
    calls = []
    monkeypatch.setattr(main, "_warm_up_client", lambda: calls.append(1))
    # Drop any handler a previous test (or arming) left on the shared server.
    main.mcp._mcp_server.notification_handlers.pop(types.InitializedNotification, None)
    yield calls
    main._warm_up_started.clear()
    main.mcp._mcp_server.notification_handlers.pop(types.InitializedNotification, None)


def _wait_for_warmup_thread():
    for thread in threading.enumerate():
        if thread.name == "ls-warmup":
            thread.join(timeout=5)


def test_start_warm_up_runs_once(_reset_state):
    main._start_warm_up()
    main._start_warm_up()
    _wait_for_warmup_thread()
    assert sum(_reset_state) == 1


def test_arm_installs_handshake_handler(_reset_state):
    assert main._arm_warm_up_after_handshake() is True
    handler = main.mcp._mcp_server.notification_handlers.get(
        types.InitializedNotification
    )
    assert handler is not None
    # Warm-up must not have started yet — only the handshake should trigger it.
    assert sum(_reset_state) == 0


def test_handshake_notification_triggers_warm_up_once(_reset_state):
    main._arm_warm_up_after_handshake()
    handler = main.mcp._mcp_server.notification_handlers[types.InitializedNotification]
    note = types.InitializedNotification(method="notifications/initialized")

    asyncio.run(handler(note))
    asyncio.run(handler(note))  # a duplicate notification must stay a no-op
    _wait_for_warmup_thread()

    assert sum(_reset_state) == 1
