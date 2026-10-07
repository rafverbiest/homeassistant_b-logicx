"""Names for the 16 B-Logicx command codes.

A datagram is two bytes. The command is the high half of the second byte,
a number from 0 to 15. The rest of the integration uses these names
("Set", "Status", "Select", …) rather than the numbers.
"""

# TCP port of a BL-NWM / BL-NWX gateway.
BLX_TCP_PORT = 10001

# High half of byte 1 → command name. See protocol.py for the byte layout.
COMMAND_CODES = {
    0: "Null",
    1: "Reset",
    2: "Toggle",
    3: "Set",
    4: "Misc",
    5: "Status",
    6: "Timer",
    7: "Value",
    8: "Dimmer",
    9: "Readout",
    10: "Teller",
    11: "System",
    12: "Settings",
    13: "Select",
    14: "Data",
    15: "Program",
}

# Name → code, used when a caller asks to send "Set" or "Status".
COMMAND_NAMES = {name: code for code, name in COMMAND_CODES.items()}
