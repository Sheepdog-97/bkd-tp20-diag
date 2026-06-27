from __future__ import annotations

# Proven/observed constants for this user's BKD ECU.
ENGINE_ADDRESS = "01"
ECU_PART = "03G 906 016 AJ"
ECU_COMPONENT = "R4 2,0L EDC G000SG"
ECU_SW_VERSION = "7341"
BOSCH_HW = "028 101 173 0"

# Blocks observed as useful/non-empty from the live runs and scans.
OBSERVED_ACTIVE_BLOCKS = [
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 15, 16, 17, 18, 20,
    21, 22, 23, 25, 26, 28, 51, 55, 56, 62, 63, 64, 80,
]

OBSERVED_EMPTY_BLOCKS = [
    14, 19, 24, 27, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40,
    41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 52, 53, 54, 57, 58, 59,
    60, 61, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79,
]

# Labels below deliberately mix confidence levels. Exact/proven means inferred from
# known behaviour + common VCDS/Ross-Tech usage + the user's own logs. Candidate means
# useful guesses from type/value patterns and should be verified.

# Curated English labels based on:
# - the user's proven raw BKD scans/live data
# - public references showing old 03G-906-016-BKD.LBL style group names
# - Ross-Tech TDI procedure notes for groups 003/011
#
# Confidence:
#   high      = verified by observed values and/or strong Ross-Tech/VCDS convention
#   medium    = public label source plus observed non-empty block on this ECU
#   candidate = useful but still verify against behaviour/VCDS if possible
BLOCK_HINTS = {
    1: {
        "name": "Injection quantity",
        "confidence": "medium",
        "fields": {
            1: "Engine speed",
            2: "Injection quantity",
            3: "Injection duration specified",
            4: "Coolant temperature",
        },
    },
    2: {
        "name": "Idle speed / pedal state",
        "confidence": "medium",
        "fields": {
            1: "Engine speed",
            2: "Accelerator pedal position",
            3: "Operating state",
            4: "Coolant temperature",
        },
    },
    3: {
        "name": "EGR / air mass",
        "confidence": "high",
        "fields": {
            1: "Engine speed",
            2: "EGR / air mass specified",
            3: "EGR / air mass actual",
            4: "EGR duty",
        },
    },
    4: {
        "name": "PD injector actuation / timing",
        "confidence": "medium",
        "fields": {
            1: "Engine speed",
            2: "Start of injection specified",
            3: "Injection duration specified",
            4: "Torsion value",
        },
    },
    5: {
        "name": "Start conditions",
        "confidence": "medium",
        "fields": {
            1: "Engine speed",
            2: "Start injection quantity",
            3: "Start synchronisation",
        },
    },
    6: {
        "name": "Status values",
        "confidence": "candidate",
        "fields": {},
    },
    7: {
        "name": "Temperature values",
        "confidence": "candidate",
        "fields": {},
    },
    8: {
        "name": "Torque limitation",
        "confidence": "medium",
        "fields": {
            1: "Engine speed",
            2: "Driver requested torque",
            3: "Torque limitation",
            4: "Smoke limitation",
        },
    },
    9: {
        "name": "Injection quantity limitation II",
        "confidence": "medium",
        "fields": {
            1: "Engine speed",
            2: "Cruise control",
            3: "Gearbox intervention torque",
            4: "Limiting torque",
        },
    },
    10: {
        "name": "Air quantities",
        "confidence": "medium",
        "fields": {
            1: "Air mass actual",
            2: "Ambient air pressure",
            3: "Boost pressure actual",
            4: "Accelerator pedal position",
        },
    },
    11: {
        "name": "Charge pressure control",
        "confidence": "high",
        "fields": {
            1: "Engine speed",
            2: "Boost specified",
            3: "Boost actual",
            4: "Boost control duty / N75",
        },
    },
    12: {
        "name": "Glow system",
        "confidence": "medium",
        "fields": {
            1: "Glow status",
            2: "Glow time",
            3: "Supply voltage",
            4: "Coolant temperature",
        },
    },
    13: {
        "name": "Idle stabilisation / injection deviation",
        "confidence": "high",
        "fields": {
            1: "Injection quantity deviation cyl. 1",
            2: "Injection quantity deviation cyl. 2",
            3: "Injection quantity deviation cyl. 3",
            4: "Injection quantity deviation cyl. 4",
        },
    },
    15: {
        "name": "Fuel consumption",
        "confidence": "medium",
        "fields": {
            1: "Engine speed",
            2: "Engine torque",
            3: "Fuel consumption",
            4: "Injection quantity driver request",
        },
    },
    16: {
        "name": "Auxiliary heater / electrical load",
        "confidence": "medium",
        "fields": {
            1: "Generator load",
            2: "Shut-off conditions",
            3: "Heater element duty/status",
            4: "Supply voltage",
        },
    },
    17: {
        "name": "Readiness code / EOBD",
        "confidence": "medium",
        "fields": {
            1: "CARB Mode 01 Data A",
            2: "CARB Mode 01 Data B",
            3: "CARB Mode 01 Data C",
            4: "CARB Mode 01 Data D",
        },
    },
    18: {
        "name": "PD solenoid valve status",
        "confidence": "medium",
        "fields": {
            1: "Solenoid valve status cyl. 1",
            2: "Solenoid valve status cyl. 2",
            3: "Solenoid valve status cyl. 3",
            4: "Solenoid valve status cyl. 4",
        },
    },
    20: {
        "name": "Torque intervention via CAN/ABS",
        "confidence": "medium",
        "fields": {
            1: "Engine speed",
            2: "Engine torque",
            3: "ASR intervention",
            4: "MSR intervention",
        },
    },
    21: {
        "name": "Powertrain CAN status",
        "confidence": "medium",
        "fields": {
            1: "Engine electronics",
            2: "Transmission electronics",
            3: "Brake electronics",
            4: "Brake electronics ESP",
        },
    },
    22: {
        "name": "Shut-off status",
        "confidence": "medium",
        "fields": {
            1: "Cruise control shut-off status",
            2: "Cruise control switch position",
            3: "Boost control shut-off status",
            4: "A/C shut-off status",
        },
    },
    23: {
        "name": "PD switching time deviation",
        "confidence": "medium",
        "fields": {
            1: "Switching time deviation cyl. 1",
            2: "Switching time deviation cyl. 2",
            3: "Switching time deviation cyl. 3",
            4: "Switching time deviation cyl. 4",
        },
    },
    25: {
        "name": "Engine speed / status",
        "confidence": "candidate",
        "fields": {
            1: "Engine speed",
        },
    },
    26: {
        "name": "Checksum",
        "confidence": "medium",
        "fields": {
            1: "Checksum",
        },
    },
    28: {
        "name": "Accelerator pedal sender",
        "confidence": "medium",
        "fields": {
            1: "Pedal sender 1",
            2: "Pedal sender 2",
            3: "Operating state",
            4: "Accelerator pedal position",
        },
    },
    51: {
        "name": "Engine speed detection / synchronisation",
        "confidence": "medium",
        "fields": {
            1: "Engine speed",
            2: "Camshaft speed",
            3: "Start synchronisation",
            4: "Injection sequence shut-off status",
        },
    },
    55: {
        "name": "ECU coding / fault path",
        "confidence": "medium",
        "fields": {
            1: "ECU coding general fault status",
            2: "ECU coding",
            3: "EEPROM fault path",
            4: "Communication fault path",
        },
    },
    56: {
        "name": "Voltage / reset fault path",
        "confidence": "medium",
        "fields": {
            1: "Voltage fault path minimum",
            2: "Voltage fault path maximum",
            3: "Shut-off status fault path",
            4: "Reset status",
        },
    },
    62: {
        "name": "Engine cooling temperatures",
        "confidence": "medium",
        "fields": {
            1: "Coolant temp engine outlet",
            2: "Coolant temp radiator outlet",
            3: "Ambient temperature",
            4: "Intake manifold temperature",
        },
    },
    63: {
        "name": "Engine cooling / A/C",
        "confidence": "medium",
        "fields": {
            1: "Refrigerant pressure",
            2: "A/C load torque",
            3: "Cooling demand",
            4: "A/C shut-off status",
        },
    },
    64: {
        "name": "Engine cooling",
        "confidence": "medium",
        "fields": {
            1: "Coolant temperature",
            2: "Coolant temp radiator outlet",
            3: "Radiator fan 1 duty",
        },
    },
    80: {
        "name": "Extended ECU identification I",
        "confidence": "high",
        "fields": {},
        "text": True,
    },
    81: {
        "name": "Extended ECU identification II",
        "confidence": "medium",
        "fields": {
            1: "VIN",
            2: "Immobiliser ID",
        },
        "text": True,
    },
    82: {
        "name": "Extended ECU identification III",
        "confidence": "medium",
        "fields": {},
        "text": True,
    },
}

PRESETS = {
    "core": {
        "blocks": [1, 3, 4, 11],
        "description": "Core idle snapshot: fuel, MAF/EGR, timing, boost",
    },
    "air": {
        "blocks": [3, 10, 11],
        "description": "Air path: EGR/MAF, air quantities, boost",
    },
    "boost": {
        "blocks": [10, 11],
        "description": "Boost diagnosis: actual air/boost and boost control",
    },
    "injectors": {
        "blocks": [13, 18, 23],
        "description": "PD injector balance/status/switching-time candidates",
    },
    "startup": {
        "blocks": [1, 4, 5, 12, 51],
        "description": "Starting/sync/glow/torsion related blocks",
    },
    "cooling": {
        "blocks": [62, 63, 64],
        "description": "Cooling temperatures, A/C load and fan duty",
    },
    "cruise": {
        "blocks": [9, 22, 28],
        "description": "Cruise/pedal/shut-off status",
    },
    "readiness": {
        "blocks": [17],
        "description": "EOBD readiness/CARB mode 01 data fields",
    },
    "version": {
        "blocks": [80, 81, 82],
        "description": "Extended ECU identification text blocks",
    },
    "road": {
        "blocks": [3, 10, 11],
        "description": "Recommended road log for MAF and boost comparison",
    },
}
