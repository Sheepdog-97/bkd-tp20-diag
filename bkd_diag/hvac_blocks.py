from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .labels import LabelStore


HVAC_MODULE_ADDRESS = "08"
HVAC_LABEL_SOURCE = "VCDS screenshots / 1K0-907-044 label family"


@dataclass(frozen=True)
class HvacBlock:
    number: int
    name: str
    fields: tuple[str, str, str, str]
    confidence: str = "label-seed"
    notes: str = ""


# Seeded from the user's VCDS measuring-block screenshots for the PQ35/Leon 1P
# Climatronic module.  These are labels, not proof that every raw value is fully
# decoded yet.  Unknown formulas intentionally remain raw/candidate in output.
HVAC_BLOCKS: dict[int, HvacBlock] = {
    1: HvacBlock(
        1,
        "General / compressor inhibit",
        (
            "Compressor Shut-Off Code",
            "Engine Speed",
            "Vehicle Speed",
            "Standing Time",
        ),
        notes="Good Open MMI truth source for compressor reason, vehicle speed and standing time.",
    ),
    2: HvacBlock(
        2,
        "Compressor",
        (
            "Compressor Current actual",
            "Compressor Current specified",
            "Compressor Rotations",
            "Compressor Load",
        ),
    ),
    3: HvacBlock(
        3,
        "Refrigerant / radiator fan / engine request",
        (
            "Refrigerant Pressure",
            "Radiator Fan Activation actual",
            "Radiator Fan Activation specified",
            "Engine Speed increase",
        ),
    ),
    4: HvacBlock(
        4,
        "Outside / intake / coolant temperatures",
        (
            "Outside Temperature unfiltered",
            "Outside Temperature regulation",
            "Fresh Air Intake Temperature",
            "Coolant Temperature",
        ),
        confidence="vcds-screenshot-label-seed",
        notes="Corrected from VCDS screenshots: group 004 is outside/unfiltered, outside/regulation, fresh-air intake and coolant temperature; group 005 is outlet/footwell temperature.",
    ),
    5: HvacBlock(
        5,
        "Outlet / footwell blower temperature",
        (
            "Left Outlet Blower Temperature",
            "Right Outlet Blower Temperature",
            "Left Footwell Blower Temperature",
            "Right Footwell Blower Temperature",
        ),
        confidence="live-confirmed-label-seed",
        notes="Live values on the SEAT were plausible outlet/footwell temperatures, unlike group 004.",
    ),
    6: HvacBlock(
        6,
        "Evaporator / cabin / sunlight",
        (
            "Evaporator Temperature",
            "Interior Temperature",
            "Left Sunlight Intensity G107",
            "Right Sunlight Intensity G134",
        ),
        notes="High-value passive-correlation target for Open MMI climate display.",
    ),
    7: HvacBlock(
        7,
        "Turbine / blower voltage",
        (
            "Turbine Voltage actual",
            "Turbine Voltage specified",
            "Turbine Load",
            "Voltage Terminal 30",
        ),
        confidence="live-corrected-label-seed",
        notes="Live SEAT data corrected field order: F2 is blower/turbine voltage specified, F3 is turbine load percentage, F4 is Terminal 30 voltage.",
    ),
    8: HvacBlock(
        8,
        "Supply / dimming",
        (
            "Voltage Terminal 15",
            "Field 2",
            "Dimming Terminal 58d",
            "Country",
        ),
        confidence="live-corrected-label-seed",
        notes="Live SEAT data corrected field order: F3 is Terminal 58d dimming percentage and F4 is country/coding value.",
    ),
    9: HvacBlock(
        9,
        "Rear window heater / auxiliary heater",
        (
            "Rear Window Heater Z2 actual",
            "Rear Window Heater Z2 specified",
            "Auxiliary Heater Status",
            "Auxiliary Heater Current",
        ),
        notes="VCDS capture proved repeated 21 09 requests and 61 09 positive responses.",
    ),
    11: HvacBlock(
        11,
        "Air recirculation flap V113 / G143",
        (
            "Potentiometer G143 Current Value",
            "Potentiometer G143 Specified Value",
            "Min Position G143 lower stop / close",
            "Max Position G143 upper stop / open",
        ),
    ),
    12: HvacBlock(
        12,
        "Left temperature flap V158 / G220",
        (
            "Potentiometer G220 Current Value",
            "Potentiometer G220 Specified Value",
            "Min Position G220 lower stop / close",
            "Max Position G220 upper stop / open",
        ),
    ),
    13: HvacBlock(
        13,
        "Right temperature flap V159 / G221",
        (
            "Potentiometer G221 Current Value",
            "Potentiometer G221 Specified Value",
            "Min Position G221 lower stop / close",
            "Max Position G221 upper stop / open",
        ),
    ),
    14: HvacBlock(
        14,
        "Center flap V70 / G112",
        (
            "Potentiometer G112 Current Value",
            "Potentiometer G112 Specified Value",
            "Min Position G112 lower stop / close",
            "Max Position G112 upper stop / open",
        ),
    ),
    15: HvacBlock(
        15,
        "Defroster flap V107 / G135",
        (
            "Potentiometer G135 Current Value",
            "Potentiometer G135 Specified Value",
            "Min Position G135 lower stop / close",
            "Max Position G135 upper stop / open",
        ),
    ),
    16: HvacBlock(
        16,
        "Air flow flap V71 / G113",
        (
            "Potentiometer G113 Current Value",
            "Potentiometer G113 Specified Value",
            "Min Position G113 lower stop / close",
            "Max Position G113 upper stop / open",
        ),
    ),
}


COMPRESSOR_SHUTOFF_CODES: dict[int, str] = {
    0: "Compressor ON",
    1: "Refrigerant pressure too high",
    2: "Blower faulty or blower voltage too low",
    3: "Refrigerant pressure too low",
    5: "Engine start not detected / runtime less than 4 seconds",
    6: "ECON mode",
    7: "Control panel OFF",
    8: "Outside temperature too low",
    10: "Supply voltage too low",
    11: "Coolant temperature too high",
    12: "Shut-off via Engine Control Module",
    13: "Supply voltage too high",
    14: "Evaporator temperature too low / icing risk",
    15: "Control module coding incorrect",
    16: "Activation signal faulty",
    17: "Refrigerant pressure sensor implausible",
}


def hvac_label_store() -> LabelStore:
    store = LabelStore(path="built-in:08-hvac-vcds-screenshot-seed", readable=True)
    store.raw_line_count = len(HVAC_BLOCKS)
    for number, block in HVAC_BLOCKS.items():
        store.group_names[number] = block.name
        for idx, label in enumerate(block.fields, start=1):
            store.groups.setdefault(number, {})[idx] = label
    return store


def hvac_catalogue_lines(blocks: Iterable[int] | None = None) -> list[str]:
    selected = sorted(HVAC_BLOCKS) if blocks is None else [b & 0xFF for b in blocks]
    lines: list[str] = [
        "08 Auto HVAC measured-value catalogue",
        f"Source: {HVAC_LABEL_SOURCE}",
        "Scope: read-only measuring-block labels and candidate decodes; raw values remain authoritative.",
        "",
    ]
    for number in selected:
        block = HVAC_BLOCKS.get(number)
        if not block:
            lines.append(f"Group {number:03d}: unknown / not yet catalogued")
            continue
        lines.append(f"Group {number:03d} — {block.name} [{block.confidence}]")
        for idx, label in enumerate(block.fields, start=1):
            lines.append(f"  F{idx}: {label}")
        if block.notes:
            lines.append(f"  notes: {block.notes}")
        lines.append("")

    lines.extend([
        "Compressor Shut-Off Code lookup (group 001 F1):",
    ])
    for code, text in sorted(COMPRESSOR_SHUTOFF_CODES.items()):
        lines.append(f"  {code:>2}: {text}")
    return lines
