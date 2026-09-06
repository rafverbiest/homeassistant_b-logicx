#!/usr/bin/env python3

"""
blxmonitor.py

Simple command-line monitor and sender for B-Logicx.

Lives with the reusable `b_logicx` library (not the Home Assistant
platform modules) so it can run without HA installed and without
shadowing the stdlib ``select`` module.

  python3 /config/custom_components/b_logicx/b_logicx/blxmonitor.py -i 192.168.50.150

Program commands and the two following datagrams are shown by default
(useful when debugging RTC sync / programming traffic).
To hide them:  --hide-program

  python3 .../b_logicx/blxmonitor.py -i 192.168.50.150 -p 10001

Log every on-screen bus line (RX + [SENT], with timestamps) to a file:

  python3 .../b_logicx/blxmonitor.py -i 192.168.50.150 -l /var/log/blxbus.log
"""

from __future__ import annotations

import argparse
import asyncio
import atexit
import os
import re
import sys
import threading
from pathlib import Path
from typing import Optional, TextIO

# Import asyncio (and thus stdlib ``select``) BEFORE putting the Home Assistant
# integration directory on sys.path. That directory contains select.py (the HA
# platform), which would otherwise shadow the stdlib and break this CLI.
#
# When this file is run as a script, sys.path[0] is this package directory
# (no select.py here), so the stdlib wins and is cached in sys.modules.

# Enable readline for command history (up/down arrows) and editing.
# This is stdlib and works on Linux/macOS. Gracefully ignored elsewhere.
try:
    import readline
    HISTFILE = os.path.expanduser("~/.blxmonitor_history")
    try:
        readline.read_history_file(HISTFILE)
    except FileNotFoundError:
        pass
    readline.set_history_length(1000)
    atexit.register(readline.write_history_file, HISTFILE)
except ImportError:
    readline = None  # No history available (e.g. Windows without pyreadline)


# Lock to serialize access to readline between the input thread and event printing.
_print_lock = threading.Lock()

# Optional append-only log of the same lines shown on screen (TX + RX).
_log_fp: Optional[TextIO] = None

# Library modules use package-relative imports; load them as ``b_logicx.*``.
_pkg_parent = Path(__file__).resolve().parent.parent
if str(_pkg_parent) not in sys.path:
    sys.path.insert(0, str(_pkg_parent))

from b_logicx.connection import BLXConnection
from b_logicx.bus_format import format_recv, format_sent
from b_logicx.const import BLX_TCP_PORT

PROMPT = "blx> "


def _log_line(text: str) -> None:
    """Append one display line to the log file (if enabled)."""
    if _log_fp is None:
        return
    try:
        _log_fp.write(text + "\n")
        _log_fp.flush()
    except Exception:
        pass


def _print_live(text: str) -> None:
    """Print output while keeping the prompt at the bottom of the terminal.

    Used for live bus events so they don't cause the 'blx> ' prompt to be
    repeated on every line.
    """
    with _print_lock:
        _log_line(text)
        if readline:
            try:
                buf = readline.get_line_buffer()
                # Clear the current prompt line completely
                line_len = len(PROMPT) + len(buf)
                sys.stdout.write("\r" + " " * line_len + "\r")
                sys.stdout.flush()

                # Print the new content
                sys.stdout.write(text + "\n")
                sys.stdout.flush()

                # Redraw the prompt + whatever the user has typed so far
                sys.stdout.write(PROMPT + buf)
                sys.stdout.flush()
                readline.redisplay()
                return
            except Exception:
                pass

        # Fallback (no readline or error)
        print(text)
        sys.stdout.flush()


def print_event(event_str: str) -> None:
    """Print a bus event with timestamp, preserving the prompt."""
    _print_live(format_recv(event_str))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="B-Logicx Monitor (uses the shared b_logicx library)"
    )
    parser.add_argument(
        "-i",
        "--ip-address",
        required=True,
        dest="ip",
        help="IP address of the BL-NWM",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=BLX_TCP_PORT,
        help=f"Port (default: {BLX_TCP_PORT})",
    )
    parser.add_argument(
        "--hide-program",
        action="store_true",
        help="Hide 'Program' commands and the two following datagrams "
             "(programming payload). By default these are shown.",
    )
    parser.add_argument(
        "-l",
        "--log-file",
        dest="log_file",
        metavar="PATH",
        help="Append every on-screen TX/RX line (with timestamps) to this file",
    )
    return parser.parse_args()


async def command_sender(conn: BLXConnection, line: str) -> None:
    """Parse a command line and send it.

    Supports both space and dot as separators:
        Set 2 80
        Set 2.80
        set 2. 80
    """
    # Split on whitespace and/or dots so "Set 2.80" and "Set 2 80" both work
    parts = re.split(r"[\s.]+", line.strip())
    if len(parts) != 3:
        print("Usage: <Command> <group> <address>   e.g. Toggle 2 3  or  Set 2.80")
        return

    cmd, g_str, a_str = parts
    cmd = cmd.title()  # Allow "set", "SET", "Toggle" etc.

    try:
        group = int(g_str)
        address = int(a_str)
    except ValueError:
        print("group and address must be integers")
        return

    try:
        await conn.send(cmd, group, address)
        _print_live(format_sent(f"{cmd} {group}.{address}"))
    except ValueError as exc:
        # Unknown command name
        print(f"Unknown command '{cmd}': {exc}")
    except Exception as exc:
        print(f"Send failed: {exc}")


async def receive_loop(conn: BLXConnection) -> None:
    """Receive events from the bus in the background.

    Events are printed with a timestamp. The printing logic ensures the
    'blx> ' prompt stays at the bottom without being duplicated.
    """
    try:
        async for event in conn.events():
            print_event(str(event))
    except Exception as exc:
        _print_live(f"Receive loop ended: {exc}")


async def run_monitor(
    ip: str,
    port: int,
    skip_programming: bool = False,
    log_file: Optional[str] = None,
) -> None:
    global _log_fp

    if log_file:
        _log_fp = open(log_file, "a", encoding="utf-8")
        print(f"Logging bus lines to {log_file}")

    try:
        print(f"Connecting to {ip}:{port} ...")
        conn = BLXConnection(ip, port, skip_programming=skip_programming)

        async with conn:
            print("Connected.")
            print("Type commands like 'Toggle 2 3' or 'Set 2.80' (dots or spaces are fine).")
            print("Type 'quit', 'q' or 'help' for more info.\n")
            if skip_programming:
                print("Program + 2 payload frames are hidden (--hide-program).\n")
            else:
                print("Program traffic is shown (use --hide-program to filter it).\n")

            print("Listening for events from the bus...")
            receiver = asyncio.create_task(receive_loop(conn))

            try:
                while True:
                    line = await asyncio.to_thread(input, PROMPT)
                    if line.strip().lower() in ("quit", "q", "exit"):
                        break
                    if line.strip().lower() == "help":
                        print("Commands: Toggle / Set / Reset / ...   group address  (e.g. Set 2.80)")
                        continue
                    await command_sender(conn, line)
            except (EOFError, KeyboardInterrupt):
                print("\nExiting...")
            finally:
                receiver.cancel()
                try:
                    await receiver
                except asyncio.CancelledError:
                    pass

        print("Disconnected.")
    finally:
        if _log_fp is not None:
            try:
                _log_fp.close()
            except Exception:
                pass
            _log_fp = None


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(
            run_monitor(
                args.ip,
                args.port,
                skip_programming=args.hide_program,
                log_file=args.log_file,
            )
        )
    except KeyboardInterrupt:
        print("\nInterrupted.")


if __name__ == "__main__":
    main()
