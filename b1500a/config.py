"""Configuration for B1500A data parsing and units."""

# Unit prefixes
UNITS = {
        "p": 1e-12,  # pico
        "n": 1e-9,   # nano
        "u": 1e-6,   # micro
        "m": 1e-3,   # milli
        "": 1,       # none (no prefix)
        "k": 1e3,    # kilo
        "M": 1e6,    # mega
        "G": 1e9,    # giga
}

# Default column names for IV sweep
IVSWEEP_VOLT_COL = "DrainV"
IVSWEEP_CURR_COL = "DrainI"

# Default column names for gate sweep
GATESWEEP_VOLT_COL = "GateV"
GATESWEEP_CURR_COL = "DrainI"

