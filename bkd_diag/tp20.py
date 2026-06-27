from __future__ import annotations

import select
import socket
import struct
import time

from .reporting import Reporter
from .utils import fmt


CAN_FRAME = "=IB3x8s"

SETUP_TX_ID = 0x200
SETUP_RX_ID = 0x201
TP_TX_ID = 0x740
TP_RX_ID = 0x300

TP_CHANNEL_PARAMS = [0xA0, 0x0F, 0x8A, 0xFF, 0x32, 0xFF]
TP_CHANNEL_TEST_RESPONSE = [0xA1, 0x0F, 0x8A, 0xFF, 0x32, 0xFF]


def pack_frame(can_id: int, data: list[int] | bytes) -> bytes:
    data = bytes(data)
    if len(data) > 8:
        raise ValueError("CAN payload too long")
    return struct.pack(CAN_FRAME, can_id, len(data), data.ljust(8, b"\x00"))


def unpack_frame(raw: bytes) -> tuple[int, bytes]:
    can_id, dlc, data = struct.unpack(CAN_FRAME, raw[:16])
    return can_id & 0x1FFFFFFF, data[:dlc]


def tp20_id_from_setup(low_byte: int, validity_prefix: int) -> tuple[int, bool]:
    """Decode an ID pair from a TP2.0 channel setup response.

    The low byte contains CAN ID bits 0-7. The low nibble of validity_prefix
    contains the high bits of the 11-bit CAN ID. The high nibble is a validity
    flag: 0 = valid, 1 = invalid/ECU decides.
    """
    can_id = ((validity_prefix & 0x0F) << 8) | (low_byte & 0xFF)
    valid = ((validity_prefix >> 4) & 0x0F) == 0
    return can_id, valid


class TP20KWP:
    def __init__(
        self,
        iface: str = "can0",
        reporter: Reporter | None = None,
        logical_address: int = 0x01,
        requested_ecu_tx_id: int = 0x300,
    ):
        self.iface = iface
        self.reporter = reporter
        self.logical_address = logical_address & 0xFF
        self.setup_rx_id = SETUP_TX_ID + self.logical_address
        self.requested_ecu_tx_id = requested_ecu_tx_id & 0x7FF

        # Updated from the D0 setup response. Engine usually negotiates
        # tester->ECU 0x740 and ECU->tester 0x300, but other modules may not.
        self.tp_tx_id = TP_TX_ID
        self.tp_rx_id = TP_RX_ID

        self.sock = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
        self.sock.bind((iface,))
        self.tx_packet_counter = 0
        self.channel_opened = False

    def send_can(self, can_id: int, data: list[int] | bytes, label: str = "TX") -> None:
        if self.reporter:
            self.reporter.trace(f"{self.reporter.colour.blue(label)} {can_id:03X} {fmt(data)}")
        self.sock.send(pack_frame(can_id, data))

    def recv_can(self, timeout: float = 1.0) -> tuple[int | None, bytes | None]:
        r, _, _ = select.select([self.sock], [], [], timeout)
        if not r:
            return None, None

        raw = self.sock.recv(16)
        can_id, data = unpack_frame(raw)

        if self.reporter:
            self.reporter.trace(f"{self.reporter.colour.magenta('RX')} {can_id:03X} {fmt(data)}")

        return can_id, data

    def handle_tp_control_frame(self, data: bytes) -> bool:
        if not data:
            return True

        first = data[0]
        if first == 0xA3:
            self.send_can(self.tp_tx_id, TP_CHANNEL_TEST_RESPONSE, label="CHAN-TEST-RESP")
            return True

        if first == 0xA8:
            raise RuntimeError("ECU closed the TP2.0 channel with A8")

        if 0xB0 <= first <= 0xBF:
            return True

        return False

    def wait_for_id(self, wanted_id: int, timeout: float = 1.0) -> bytes:
        deadline = time.time() + timeout
        while time.time() < deadline:
            can_id, data = self.recv_can(max(0.0, deadline - time.time()))
            if can_id is None:
                break

            if can_id == self.tp_rx_id and data is not None:
                self.handle_tp_control_frame(data)

            if can_id == wanted_id and data is not None:
                return data

        raise TimeoutError(f"Timed out waiting for CAN ID 0x{wanted_id:X}")

    def drain_rx(self, timeout: float = 0.05) -> int:
        """Drain stale frames before a fresh setup/session attempt."""
        drained = 0
        deadline = time.time() + timeout
        while time.time() < deadline:
            can_id, data = self.recv_can(max(0.0, deadline - time.time()))
            if can_id is None or data is None:
                break
            drained += 1
        if drained and self.reporter:
            self.reporter.detail(f"Drained {drained} stale CAN frame(s)")
        return drained

    def recv_any_until(self, timeout: float = 1.0) -> list[tuple[int, bytes]]:
        frames: list[tuple[int, bytes]] = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            can_id, data = self.recv_can(max(0.0, deadline - time.time()))
            if can_id is None or data is None:
                break
            frames.append((can_id, data))
        return frames

    def build_setup_request(self, logical_address: int | None = None, requested_ecu_tx_id: int | None = None) -> list[int]:
        logical = self.logical_address if logical_address is None else (logical_address & 0xFF)
        requested = self.requested_ecu_tx_id if requested_ecu_tx_id is None else (requested_ecu_tx_id & 0x7FF)
        return [
            logical,
            0xC0,
            0x00,
            0x10,
            requested & 0xFF,
            (requested >> 8) & 0x0F,
            0x01,
        ]

    def try_setup_only(self, setup_tx_id: int = SETUP_TX_ID, requested_ecu_tx_id: int | None = None, timeout: float = 0.6) -> list[tuple[int, bytes]]:
        """Send only a TP2.0 channel setup request and return all frames seen.

        This does not send channel parameters or KWP session-open. It is intended
        for safe discovery when a non-engine module does not answer the known
        engine setup path.
        """
        req = self.build_setup_request(requested_ecu_tx_id=requested_ecu_tx_id)
        self.drain_rx(timeout=0.05)
        self.send_can(setup_tx_id, req, label="SETUP-PROBE")
        frames = self.recv_any_until(timeout=timeout)

        for _can_id, data in frames:
            if len(data) >= 7 and data[1] == 0xD0:
                ecu_tx_id, ecu_tx_valid = tp20_id_from_setup(data[2], data[3])
                tester_tx_id, tester_tx_valid = tp20_id_from_setup(data[4], data[5])
                if ecu_tx_valid and tester_tx_valid:
                    self.tp_rx_id = ecu_tx_id
                    self.tp_tx_id = tester_tx_id
                    self.channel_opened = True
                break

        return frames


    def open(self, session: int = 0x89, start_session: bool = True) -> None:
        if self.reporter:
            self.reporter.header("Opening TP2.0 / KWP2000 session")
            self.reporter.info(f"Logical address: 0x{self.logical_address:02X}")

        setup_request = [
            self.logical_address,
            0xC0,
            0x00,
            0x10,  # RX invalid: let the ECU decide where it listens
            self.requested_ecu_tx_id & 0xFF,
            (self.requested_ecu_tx_id >> 8) & 0x0F,  # valid requested ECU TX ID
            0x01,
        ]

        self.drain_rx(timeout=0.05)
        self.send_can(SETUP_TX_ID, setup_request)
        setup = self.wait_for_id(self.setup_rx_id, timeout=1.0)
        if len(setup) < 7 or setup[1] != 0xD0:
            raise RuntimeError(
                f"Unexpected TP2.0 setup response from logical 0x{self.logical_address:02X}: {fmt(setup)}"
            )

        ecu_tx_id, ecu_tx_valid = tp20_id_from_setup(setup[2], setup[3])
        tester_tx_id, tester_tx_valid = tp20_id_from_setup(setup[4], setup[5])
        if not ecu_tx_valid or not tester_tx_valid:
            raise RuntimeError(f"TP2.0 setup response did not contain valid negotiated IDs: {fmt(setup)}")

        self.tp_rx_id = ecu_tx_id
        self.tp_tx_id = tester_tx_id
        self.channel_opened = True

        if self.reporter:
            self.reporter.ok("TP2.0 channel setup accepted")
            self.reporter.detail(f"Negotiated ECU→tester CAN ID: 0x{self.tp_rx_id:03X}")
            self.reporter.detail(f"Negotiated tester→ECU CAN ID: 0x{self.tp_tx_id:03X}")

        self.send_can(self.tp_tx_id, TP_CHANNEL_PARAMS)
        params = self.wait_for_id(self.tp_rx_id, timeout=1.0)
        if not params or params[0] != 0xA1:
            raise RuntimeError(f"Unexpected TP2.0 parameter response: {fmt(params)}")
        if self.reporter:
            self.reporter.ok("TP2.0 channel parameters accepted")

        if not start_session:
            if self.reporter:
                self.reporter.warn("KWP StartDiagnosticSession skipped by request")
            return

        resp = self.kwp_request([0x10, session], timeout=2.0)
        if resp != bytes([0x50, session]):
            raise RuntimeError(f"Unexpected KWP session response: {fmt(resp)}")
        if self.reporter:
            self.reporter.ok(f"KWP session opened: 10 {session:02X} → 50 {session:02X}")

    def close(self) -> None:
        try:
            if self.channel_opened:
                self.send_can(self.tp_tx_id, [0xA8], label="CLOSE")
                self.channel_opened = False
        except Exception:
            pass
        finally:
            try:
                self.sock.close()
            except Exception:
                pass

    def send_tp_data(self, kwp_payload: list[int] | bytes) -> None:
        kwp_payload = bytes(kwp_payload)
        if len(kwp_payload) > 5:
            raise NotImplementedError("Short request path currently supports KWP requests up to 5 bytes")

        op_seq = 0x10 | (self.tx_packet_counter & 0x0F)
        frame = [op_seq, (len(kwp_payload) >> 8) & 0xFF, len(kwp_payload) & 0xFF] + list(kwp_payload)
        self.send_can(self.tp_tx_id, frame)
        self.tx_packet_counter = (self.tx_packet_counter + 1) & 0x0F

    def ack_ecu_data_frame(self, first_byte: int) -> None:
        seq = first_byte & 0x0F
        ack = 0xB0 | ((seq + 1) & 0x0F)
        self.send_can(self.tp_tx_id, [ack], label="ACK")

    def recv_kwp_response(self, timeout: float = 3.0) -> bytes:
        payload = bytearray()
        expected_len: int | None = None
        deadline = time.time() + timeout

        while time.time() < deadline:
            can_id, data = self.recv_can(max(0.0, deadline - time.time()))
            if can_id is None or data is None:
                break

            if can_id != self.tp_rx_id or not data:
                continue

            first = data[0]
            high = first & 0xF0

            if self.handle_tp_control_frame(data):
                continue

            if high == 0x10:
                if expected_len is None:
                    if len(data) < 3:
                        continue
                    expected_len = ((data[1] & 0x7F) << 8) | data[2]
                    payload.extend(data[3:])
                else:
                    payload.extend(data[1:])

                self.ack_ecu_data_frame(first)
                if expected_len is not None and len(payload) >= expected_len:
                    return bytes(payload[:expected_len])
                continue

            if high == 0x20:
                if expected_len is None:
                    if len(data) < 3:
                        continue
                    expected_len = ((data[1] & 0x7F) << 8) | data[2]
                    payload.extend(data[3:])
                else:
                    payload.extend(data[1:])

                self.ack_ecu_data_frame(first)
                if expected_len is not None and len(payload) >= expected_len:
                    return bytes(payload[:expected_len])
                continue

            if self.reporter:
                self.reporter.trace(f"Unhandled TP2.0 frame on 0x{self.tp_rx_id:03X}: {fmt(data)}")

        raise TimeoutError("Timed out waiting for KWP response")

    def kwp_request(self, kwp_payload: list[int] | bytes, timeout: float = 3.0) -> bytes:
        self.send_tp_data(kwp_payload)
        deadline = time.time() + timeout

        while time.time() < deadline:
            resp = self.recv_kwp_response(timeout=max(0.1, deadline - time.time()))
            if len(resp) >= 3 and resp[0] == 0x7F and resp[2] == 0x78:
                if self.reporter:
                    self.reporter.warn(f"KWP response pending: {fmt(resp)}")
                deadline = time.time() + timeout
                continue
            return resp

        raise TimeoutError("Timed out waiting for KWP response")
