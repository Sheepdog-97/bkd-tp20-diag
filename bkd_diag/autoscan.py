from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AutoScanModule:
    address: str
    name: str
    label: str = ""
    part_number: str = ""
    hw: str = ""
    component: str = ""
    coding: str = ""
    fault_status: str = ""
    gateway_status: str = ""
    faults: list[dict] = field(default_factory=list)


@dataclass
class AutoScan:
    vin: str = ""
    mileage: str = ""
    chassis: str = ""
    scan: str = ""
    modules: dict[str, AutoScanModule] = field(default_factory=dict)


def parse_autoscan_text(text: str) -> AutoScan:
    vin_m = re.search(r"VIN:\s*([A-Z0-9]+).*?Mileage:\s*([0-9]+km-[0-9]+miles)", text, re.S)
    vin = vin_m.group(1) if vin_m else ""
    mileage = vin_m.group(2) if vin_m else ""
    chassis_lines = re.findall(r"Chassis Type:\s*(.+)", text)
    scan_lines = re.findall(r"Scan:\s*(.+)", text)

    statuses = {}
    for addr, name, status in re.findall(r"^([0-9A-F]{2})-([^-]+?) -- Status: (.+)$", text, re.M):
        statuses[addr] = {"name": name.strip(), "status": status.strip()}

    modules: dict[str, AutoScanModule] = {}

    # Split around address blocks. Keep last block for each address because Auto-Scans
    # sometimes contain before/after scans in one file.
    blocks = re.split(r"\n-{10,}\n", text)
    for block in blocks:
        mm = re.search(r"Address\s+([0-9A-F]{2}):\s*([^\n]+?)(?:\s+Labels:\.?\s*([^\n]+))?\n", block)
        if not mm:
            continue

        addr = mm.group(1)
        name = mm.group(2).strip()
        label = (mm.group(3) or "").strip()

        part_number = ""
        hw = ""
        part_m = re.search(r"Part No(?: SW)?:\s*([^\n]+?)(?:\s+HW:\s*([^\n]+))?\n", block)
        if part_m:
            part_number = part_m.group(1).strip()
            hw = (part_m.group(2) or "").strip()

        comp_m = re.search(r"Component:\s*([^\n]+)", block)
        component = comp_m.group(1).strip() if comp_m else ""

        coding_m = re.search(r"Coding:\s*([A-Fa-f0-9]+)", block)
        coding = coding_m.group(1).strip() if coding_m else ""

        faults = []
        for fm in re.finditer(r"(?m)^(\d{5}) - ([^\n]+)\n\s+([0-9A-F]{3}) - ([^\n]+)", block):
            faults.append({
                "code": fm.group(1),
                "text": fm.group(2).strip(),
                "subcode": fm.group(3),
                "subtext": fm.group(4).strip(),
            })

        if "No fault code found" in block:
            fault_status = "No fault code found"
        elif "Cannot be reached" in block:
            fault_status = "Cannot be reached"
        elif faults:
            fault_status = f"{len(faults)} fault(s)"
        else:
            fault_status = "Unknown"

        modules[addr] = AutoScanModule(
            address=addr,
            name=name,
            label=label,
            part_number=part_number,
            hw=hw,
            component=component,
            coding=coding,
            fault_status=fault_status,
            gateway_status=statuses.get(addr, {}).get("status", ""),
            faults=faults,
        )

    return AutoScan(
        vin=vin,
        mileage=mileage,
        chassis=chassis_lines[-1].strip() if chassis_lines else "",
        scan=scan_lines[-1].strip() if scan_lines else "",
        modules=modules,
    )


def load_autoscan(path: str | Path) -> AutoScan:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return parse_autoscan_text(text)


def load_default_autoscan() -> AutoScan:
    data_path = Path(__file__).resolve().parent.parent / "data" / "autoscan_default.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    scan = AutoScan(
        vin=data.get("vin", ""),
        mileage=data.get("mileage", ""),
        chassis=data.get("chassis", ""),
        scan=data.get("scan", ""),
    )
    for addr, module in data.get("modules", {}).items():
        scan.modules[addr] = AutoScanModule(address=addr, **{k: v for k, v in module.items() if k != "address"})
    return scan
