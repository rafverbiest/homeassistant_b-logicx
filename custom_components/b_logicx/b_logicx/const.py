"""Constants for the B-Logicx protocol."""

BLX_TCP_PORT = 10001

# Command codes (high nibble of second byte)
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

# Reverse mapping: name -> code
COMMAND_NAMES = {name: code for code, name in COMMAND_CODES.items()}
