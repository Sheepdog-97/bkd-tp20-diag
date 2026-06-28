from __future__ import annotations

from .reporting import Reporter
from .tp20 import TP20KWP, tp20_id_from_setup
from .utils import fmt
from .module_probe import module_open_kwargs, resolve_module_profile


SAFE_SETUP_TX_IDS = [0x200]
SAFE_REQUESTED_ECU_TX_IDS = [0x300, 0x740]


def resolve_logical_address(module_key: str) -> tuple[int, object | None]:
    return resolve_module_profile(module_key)


def looks_like_setup_response(data: bytes) -> bool:
    return len(data) >= 7 and data[1] == 0xD0


def describe_setup_response(can_id: int, data: bytes) -> str:
    if not looks_like_setup_response(data):
        return ""

    ecu_tx_id, ecu_valid = tp20_id_from_setup(data[2], data[3])
    tester_tx_id, tester_valid = tp20_id_from_setup(data[4], data[5])
    return (
        f"D0 setup response on 0x{can_id:03X}: "
        f"ECU→tester=0x{ecu_tx_id:03X} valid={ecu_valid}, "
        f"tester→ECU=0x{tester_tx_id:03X} valid={tester_valid}"
    )


def run_setup_discovery(
    iface: str,
    reporter: Reporter,
    module_key: str,
    timeout: float = 0.7,
    include_engine_reference: bool = False,
) -> bool:
    logical, module = resolve_logical_address(module_key)

    reporter.header(f"TP2.0 setup discovery for 0x{logical:02X}")
    if module:
        reporter.line(f"Module:      {module.name}")
        reporter.line(f"Part number: {reporter.colour.green(module.part_number) if module.part_number else reporter.colour.dim('unknown')}")
        reporter.line(f"Role:        {module.role}")
    reporter.warn("Discovery sends TP2.0 setup frames only. It does not open KWP or send diagnostic services.")

    found = False
    probe_addresses = [logical]
    if include_engine_reference and logical != 0x01:
        probe_addresses.insert(0, 0x01)

    for logical_addr in probe_addresses:
        if logical_addr != logical:
            reporter.header("Reference setup probe: engine 0x01")

        for setup_tx_id in SAFE_SETUP_TX_IDS:
            for requested_id in SAFE_REQUESTED_ECU_TX_IDS:
                reporter.line(
                    f"Probe logical=0x{logical_addr:02X} setup_tx=0x{setup_tx_id:03X} "
                    f"requested_ecu_tx=0x{requested_id:03X}"
                )

                ecu = TP20KWP(
                    iface=iface,
                    reporter=reporter,
                    logical_address=logical_addr,
                    requested_ecu_tx_id=requested_id,
                )
                try:
                    frames = ecu.try_setup_only(
                        setup_tx_id=setup_tx_id,
                        requested_ecu_tx_id=requested_id,
                        timeout=timeout,
                    )
                finally:
                    ecu.close()

                if not frames:
                    reporter.line("  no frames seen")
                    continue

                for can_id, data in frames:
                    desc = describe_setup_response(can_id, data)
                    if desc:
                        found = True
                        reporter.ok("  " + desc)
                    else:
                        reporter.line(f"  frame 0x{can_id:03X}: {fmt(data)}")

    if not found:
        reporter.warn("No TP2.0 D0 setup response found for the tested variants.")
        reporter.info("Next step: sniff VCDS connecting to this module, or try a broader read-only setup-ID sweep.")
    return found
