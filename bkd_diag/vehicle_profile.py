from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModuleProfile:
    address: str
    name: str
    part_number: str
    role: str
    status: str = "profiled"
    likely_protocol: str = "unknown"
    label_candidates: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""


VIN = "VSSZZZ1PZ6R000000"
VIN_SPACED = "VSS ZZZ 1P Z6R 000 000"
PLATFORM = "SEAT Leon 1P / PQ35"
ENGINE_CODE = "BKD"
KNOWN_ENGINE_ECU = "03G 906 016 AJ"

MODULES = [
    ModuleProfile(
        "01", "Engine", "03G 906 016 AJ", "BKD 2.0 TDI EDC16 engine ECU",
        likely_protocol="VW TP2.0/KWP2000 proven",
        label_candidates=("03G-906-016-BKD.clb", "03G-906-016-BKC.clb", "03G-906-016-BKE.clb", "03G-906-016-BDJ.clb", "03G-906-016-BRE.clb"),
        notes="Engine communication proven on the development vehicle. Current tool is mature for this module.",
    ),
    ModuleProfile(
        "03", "ABS Brakes", "1K0 907 379 Q", "ABS/ESP brake electronics",
        likely_protocol="likely TP2.0/KWP on early PQ35; verify",
        label_candidates=("1K0-907-379-MK60-A.clb", "1K0-907-379-MK70.clb", "1K0-907-379-MK70M.clb", "1K0-907-37x-ABS.clb", "1K0-907-37x-ESP-A.clb", "1K0-907-37x-ESP-F.clb"),
    ),
    ModuleProfile(
        "08", "Auto HVAC", "1P0 907 044", "Climatronic/HVAC",
        likely_protocol="likely TP2.0/KWP or module-specific KWP; verify",
        label_candidates=("1K-08.clb",),
    ),
    ModuleProfile(
        "09", "Central Electrics", "3C0 937 049 E", "Central electronics/BCM",
        likely_protocol="likely TP2.0/KWP; verify",
        label_candidates=("3C0-937-049-23-M.lbl", "3C0-937-049-30-H.lbl", "3C0-937-049.clb", "1K0-937-08x-09.clb"),
    ),
    ModuleProfile(
        "09-sub1", "Wiper/Subsystem", "1P0 955 119 A", "Central electric subsystem/wiper",
        likely_protocol="subsystem behind 09",
        label_candidates=("1P0-955-119.clb", "1K0-955-119.clb"),
        notes="May not be directly addressable as a diagnostic control module.",
    ),
    ModuleProfile(
        "15", "Airbags", "3C0 909 605 E", "Airbag control module",
        likely_protocol="KWP/TP2.0 likely; do read-only only",
        label_candidates=("3C0-909-605.clb", "1K0-909-605.lbl"),
        notes="Safety module. Avoid coding/adaptations until read-only support is proven.",
    ),
    ModuleProfile(
        "16", "Steering Wheel", "1K0 953 549 AG", "Steering wheel electronics",
        likely_protocol="likely TP2.0/KWP; verify",
        label_candidates=("1K0-953-549-MY9.lbl", "1K-16.clb"),
    ),
    ModuleProfile(
        "17", "Instruments", "1P0 920 923 C", "Instrument cluster",
        likely_protocol="likely TP2.0/KWP; verify",
        label_candidates=("1P0-920-xxx-17.clb", "1K0-920-xxx-17.lbl", "1K-17.lbl"),
    ),
    ModuleProfile(
        "19", "CAN Gateway", "1K0 907 530 F", "CAN gateway",
        likely_protocol="likely TP2.0/KWP; verify",
        label_candidates=("1K0-907-530-V2.clb", "1K0-907-530-V3.clb", "1K0-907-530-V4.clb", "1K-19.lbl"),
    ),
    ModuleProfile(
        "25", "Immobilizer", "1P0 920 923 C", "Immobilizer inside instrument cluster",
        likely_protocol="cluster/immobilizer path; verify",
        label_candidates=("1P0-920-xxx-25.clb", "1K0-920-xxx-25.clb", "1K-25.lbl"),
        notes="Part number shared with instruments; may be separate logical address but same hardware.",
    ),
    ModuleProfile(
        "42", "Driver Door", "1T0 959 701 C", "Driver door electronics",
        likely_protocol="likely TP2.0/KWP; verify",
        label_candidates=("1K0-959-701-MAX1.lbl", "1K0-959-701-MAX3.clb", "1K0-959-701-MIN1.lbl", "1K0-959-701-MIN2.lbl", "1K0-959-701-MIN3.clb", "1T0-959-701.clb"),
    ),
    ModuleProfile(
        "44", "Steering Assist", "1K2 909 144 J", "Electromechanical steering assist",
        likely_protocol="likely TP2.0/KWP; verify",
        label_candidates=("1K0-909-14x-GEN3.clb", "1K-44.clb"),
    ),
    ModuleProfile(
        "46", "Central Convenience", "1K0 959 433 AK", "Comfort/convenience module",
        likely_protocol="likely TP2.0/KWP; verify",
        label_candidates=("1K0-959-433-MAX.clb", "1K-46.clb"),
    ),
    ModuleProfile(
        "52", "Passenger Door", "1T0 959 702 C", "Passenger door electronics",
        likely_protocol="likely TP2.0/KWP; verify",
        label_candidates=("1K0-959-702-MAX1.lbl", "1K0-959-702-MAX3.clb", "1K0-959-702-MIN1.lbl", "1K0-959-702-MIN2.lbl", "1K0-959-702-MIN3.clb", "1T0-959-702.clb"),
    ),
    ModuleProfile(
        "56", "Radio", "", "Radio / infotainment head unit",
        status="cannot be reached in Auto-Scan",
        likely_protocol="not reachable on current vehicle scan",
        label_candidates=("1K0-035-1xx-56.clb", "1K0-035-18x-56.clb", "1K0-035-095.lbl", "1K0-035-161.lbl"),
        notes="VCDS Auto-Scan reports Address 56 cannot be reached; gateway also reports 01304 Radio and 01305 infotainment databus faults.",
    ),
    ModuleProfile(
        "62", "Rear Left Door", "1K0 959 703 G", "Rear left door electronics",
        likely_protocol="likely TP2.0/KWP; verify",
        label_candidates=("1K0-959-703-GEN1.lbl", "1K0-959-703-GEN3.clb", "1K0-959-70x-GEN4.clb"),
    ),
    ModuleProfile(
        "72", "Rear Right Door", "1K0 959 704 G", "Rear right door electronics",
        likely_protocol="likely TP2.0/KWP; verify",
        label_candidates=("1K0-959-704-GEN1.lbl", "1K0-959-704-GEN3.clb", "1K0-959-70x-GEN4.clb"),
    ),
]

MODULE_BY_ADDRESS = {m.address: m for m in MODULES}
MODULE_BY_NAME = {m.name.lower(): m for m in MODULES}


def find_module(key: str) -> ModuleProfile | None:
    key_norm = key.strip().lower()
    if key_norm in MODULE_BY_ADDRESS:
        return MODULE_BY_ADDRESS[key_norm]
    for module in MODULES:
        if key_norm == module.name.lower() or key_norm in module.name.lower() or key_norm == module.part_number.lower():
            return module
    return None


def profile_lines(detail: bool = False) -> list[str]:
    lines = [
        f"Vehicle: {PLATFORM}",
        f"VIN:     {VIN}",
        f"Engine:  {ENGINE_CODE}",
        "",
        "Modules:",
    ]
    for m in MODULES:
        lines.append(f"  {m.address:<7} {m.name:<22} {m.part_number:<16} {m.role}")
        if detail:
            lines.append(f"          protocol: {m.likely_protocol}")
            if m.label_candidates:
                lines.append(f"          labels:   {', '.join(m.label_candidates)}")
            if m.notes:
                lines.append(f"          notes:    {m.notes}")
    return lines


def module_probe_plan_lines() -> list[str]:
    lines = [
        "Future multi-module probe plan",
        "",
        "1. Keep engine module 01 as the stable baseline.",
        "2. Add generic TP2.0 setup using logical address byte per module.",
        "3. For each module, first test only open-session + ident/read-faults.",
        "4. Do not implement coding, output tests, adaptations or basic settings until read-only is proven.",
        "5. Especially treat airbags, ABS and immobilizer as read-only/safety-sensitive modules.",
        "",
        "Suggested first expansion order:",
        "  19 CAN Gateway       low-risk, useful for installed-list discovery",
        "  17 Instruments       useful ident/immobilizer context",
        "  03 ABS               useful DTCs, but safety-critical/read-only",
        "  08 HVAC              useful and usually low-risk",
        "  09 Central Electrics useful but broad coding/adaptation surface",
        "  42/52/62/72 Doors    useful convenience data, lower priority",
    ]
    return lines


# Exact VCDS Auto-Scan labels/components from the uploaded 2024-07-05 scans.
AUTOSCAN_LABELS = {
    "56": "",
    "01": "03G-906-016-BKD.clb",
    "03": "1K0-907-379-MK60-F.clb",
    "08": "1K0-907-044.lbl",
    "09": "3C0-937-049-23-H.lbl",
    "09-sub1": "1KX-955-119.CLB",
    "15": "3C0-909-605.lbl",
    "16": "1K0-953-549-MY8.lbl",
    "17": "1K0-920-xxx-17.lbl",
    "19": "1K0-907-530-V1.clb",
    "25": "1K0-920-xxx-25.clb",
    "42": "1K0-959-701-MAX2.lbl",
    "44": "1Kx-909-144-G2V2.clb",
    "46": "1K0-959-433-MIN.clb",
    "52": "1K0-959-702-MAX2.lbl",
    "62": "1K0-959-703-GEN2.lbl",
    "72": "1K0-959-704-GEN2.lbl",
}

AUTOSCAN_COMPONENTS = {
    "56": "Cannot be reached",
    "01": "R4 2,0L EDC G000SG 7341",
    "03": "ESP FRONT MK60 0102",
    "08": "ClimatronicPQ35 001 0302",
    "09": "Bordnetz-SG H37 1002",
    "15": "T9 AIRBAG VW8 027 2421",
    "16": "J0527 634 0070",
    "17": "KOMBIINSTRUMENT VO3 0618",
    "19": "Gateway H10 0120",
    "25": "IMMO VO3 0618",
    "42": "Tuer-SG 024 2452",
    "44": "EPS_ZFLS Kl.4 D04 1606",
    "46": "KSG 0401",
    "52": "Tuer-SG 024 2452",
    "62": "Tuer-SG 021 2420",
    "72": "Tuer-SG 021 2420",
}

AUTOSCAN_KNOWN_CURRENT_FAULTS = {
    "17": ["00003 - Control Module: 014 - Defective"],
    "19": [
        "01305 - Databus for Infotainment: 004 - No Signal/Communication",
        "01304 - Radio: 004 - No Signal/Communication",
    ],
    "46": [
        "01135 - Interior Monitoring Sensors: 004 - No Signal/Communication",
        "01134 - Alarm Horn (H12): 004 - No Signal/Communication",
    ],
    "56": ["Radio cannot be reached"],
}
