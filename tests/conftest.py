"""Pytest fixtures for offline B-Logicx tests (no Home Assistant required)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent

# Prefer library + pure modules from integration root; load fixtures from tests/
for p in (str(ROOT), str(TESTS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from fake_gateway import FakeGateway  # noqa: E402


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--bus-log",
        action="store_true",
        default=False,
        help=(
            "Print a blxmonitor-style bus transcript for FakeGateway tests "
            "(also: env BLX_BUS_LOG=1). Failed tests always dump the log."
        ),
    )


def _want_bus_log(config: pytest.Config) -> bool:
    if config.getoption("--bus-log", default=False):
        return True
    return os.environ.get("BLX_BUS_LOG", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    """Stash per-phase reports so fixtures can dump bus log on failure."""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


def _dump_bus_log(gw: FakeGateway, test_name: str) -> None:
    if not gw.bus_log:
        print(f"\n--- bus log ({test_name}): (empty) ---", flush=True)
        return
    print(f"\n--- bus log ({test_name}) ---", flush=True)
    for line in gw.bus_log:
        print(line, flush=True)
    print("--- end bus log ---", flush=True)


@pytest_asyncio.fixture
async def fake_gateway(request: pytest.FixtureRequest):
    """Start a FakeGateway; yield it; stop on teardown.

    Clears BLXConnection singletons so each test gets a clean client.

    Bus log (blxmonitor-style):
    - Live lines when ``--bus-log`` or ``BLX_BUS_LOG=1``
    - Full dump on test failure (always)
    """
    from b_logicx.connection import BLXConnection

    BLXConnection._active_connections.clear()
    BLXConnection._connect_locks.clear()

    gw = FakeGateway()
    live = _want_bus_log(request.config)
    if live:
        gw.on_bus_log(lambda line: print(line, flush=True))

    await gw.start()
    try:
        yield gw
    finally:
        rep_call = getattr(request.node, "rep_call", None)
        failed = rep_call is not None and rep_call.failed
        # Live mode already printed each line; still dump on failure for a
        # single block under the assertion, and dump on success only if live
        # was not used (shouldn't happen). Prefer one tidy block on failure.
        if failed:
            _dump_bus_log(gw, request.node.name)
        elif live and gw.bus_log:
            # Teardown banner so green --bus-log runs still show a labeled log
            # without duplicating every line (live already printed them).
            print(
                f"--- bus log end ({request.node.name}, "
                f"{len(gw.bus_log)} lines) ---",
                flush=True,
            )

        await gw.stop()
        BLXConnection._active_connections.clear()
        BLXConnection._connect_locks.clear()


@pytest.fixture
def fixtures_dir() -> Path:
    return TESTS_DIR / "fixtures"
