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

# Engine-side testing originally proved this response.  The VCDS ABS/non-engine
# splitter traces later showed a different tester response while those modules
# were in long pending waits.  Keep both so engine behaviour is not regressed.
TP_CHANNEL_TEST_RESPONSE_ENGINE = [0xA1, 0x0F, 0x8A, 0xFF, 0x32, 0xFF]
TP_CHANNEL_TEST_RESPONSE_VCDS_MODULE = [0xA1, 0x0F, 0x64, 0x9C, 0x0A, 0x9C]
TP_CHANNEL_TEST_RESPONSE = TP_CHANNEL_TEST_RESPONSE_ENGINE


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
        channel_test_response: list[int] | bytes | None = None,
        min_kwp_gap: float = 0.0,
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
        self.channel_test_response = list(channel_test_response or TP_CHANNEL_TEST_RESPONSE)
        self.pending_response_count = 0
        # Some non-engine PQ35 modules accept session open but ignore the very
        # next KWP request if it is sent immediately. VCDS leaves a small
        # application-layer gap after ACKing 50 89 / multi-frame replies.
        # Engine remains at 0.0 so known-good behaviour is preserved.
        self.min_kwp_gap = max(0.0, float(min_kwp_gap))
        self._last_kwp_activity_at = 0.0

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
            # VCDS ABS/non-engine captures show that when the ECU sends A3
            # during a long pending KWP wait, the tester answers with its own
            # timing/test parameters, not the ECU's A1 response bytes.
            self.send_can(self.tp_tx_id, self.channel_test_response, label="CHAN-TEST-RESP")
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

    def drain_transport_quiet(self, timeout: float = 0.5) -> int:
        """Drain TP2.0 traffic while replying to transport housekeeping.

        This is used before/after closing sensitive modules such as ABS. It
        does not send diagnostic KWP services. It only ACKs data frames and
        answers ECU-side A3 channel tests so the module has a chance to settle
        before the socket is closed.
        """
        count = 0
        deadline = time.time() + max(0.0, timeout)
        while time.time() < deadline:
            can_id, data = self.recv_can(max(0.0, deadline - time.time()))
            if can_id is None or data is None:
                break
            if can_id != self.tp_rx_id or not data:
                continue

            first = data[0]
            high = first & 0xF0
            if first == 0xA8:
                self.channel_opened = False
                count += 1
                break
            if self.handle_tp_control_frame(data):
                count += 1
                continue
            if high in (0x10, 0x20):
                self.ack_ecu_data_frame(first)
                count += 1
                continue
            count += 1
        if count and self.reporter:
            self.reporter.detail(f"Graceful close drained {count} TP2.0 frame(s)")
        return count

    def graceful_close(self, pre_drain: float = 0.4, post_drain: float = 1.0) -> None:
        """Close a TP2.0 channel with a small quiet/drain window.

        VCDS appears to leave some modules, especially ABS/ESP, time to leave
        their visible diagnostic communication state. This helper is still only
        TP2.0 transport cleanup: no coding, adaptations, output tests, or clear
        services are sent.
        """
        try:
            if not self.channel_opened:
                return
            self.drain_transport_quiet(timeout=pre_drain)
            self.send_can(self.tp_tx_id, [0xA8], label="CLOSE")
            self.channel_opened = False
            self.drain_transport_quiet(timeout=post_drain)
        except Exception:
            # Close paths must never mask the original command result.
            pass

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

    def wait_kwp_gap(self) -> None:
        if self.min_kwp_gap <= 0:
            return
        if self._last_kwp_activity_at <= 0:
            return
        remaining = self.min_kwp_gap - (time.time() - self._last_kwp_activity_at)
        if remaining > 0:
            if self.reporter:
                self.reporter.detail(f"VCDS-like KWP pacing gap: {remaining:.3f}s")
            time.sleep(remaining)

    def send_tp_data(self, kwp_payload: list[int] | bytes) -> None:
        self.wait_kwp_gap()
        kwp_payload = bytes(kwp_payload)
        if len(kwp_payload) > 5:
            raise NotImplementedError("Short request path currently supports KWP requests up to 5 bytes")

        op_seq = 0x10 | (self.tx_packet_counter & 0x0F)
        frame = [op_seq, (len(kwp_payload) >> 8) & 0xFF, len(kwp_payload) & 0xFF] + list(kwp_payload)
        self.send_can(self.tp_tx_id, frame)
        self._last_kwp_activity_at = time.time()
        self.tx_packet_counter = (self.tx_packet_counter + 1) & 0x0F

    def ack_ecu_data_frame(self, first_byte: int) -> None:
        seq = first_byte & 0x0F
        ack = 0xB0 | ((seq + 1) & 0x0F)
        self.send_can(self.tp_tx_id, [ack], label="ACK")
        self._last_kwp_activity_at = time.time()

    def recv_kwp_response(self, timeout: float = 3.0, control_extend: float = 0.75, max_control_extra: float = 6.0) -> bytes:
        payload = bytearray()
        expected_len: int | None = None
        frame_count = 0
        started_at = time.time()
        deadline = started_at + timeout
        hard_deadline = started_at + timeout + max_control_extra

        while time.time() < deadline:
            can_id, data = self.recv_can(max(0.0, deadline - time.time()))
            if can_id is None or data is None:
                break

            if can_id != self.tp_rx_id or not data:
                continue

            first = data[0]
            high = first & 0xF0

            if self.handle_tp_control_frame(data):
                # A3/Bx/A8 are transport/control traffic, not KWP application
                # responses.  VCDS keeps waiting after A3 channel tests; extend
                # a little so a late 50/58/5A response is not missed.
                if first == 0xA3:
                    deadline = min(max(deadline, time.time() + control_extend), hard_deadline)
                continue

            if high == 0x10:
                if expected_len is None:
                    if len(data) < 3:
                        continue
                    expected_len = ((data[1] & 0x7F) << 8) | data[2]
                    payload.extend(data[3:])
                else:
                    payload.extend(data[1:])

                frame_count += 1
                self.ack_ecu_data_frame(first)
                if expected_len is not None and len(payload) >= expected_len:
                    if frame_count > 1 and self.reporter:
                        self.reporter.detail(f"Reassembled {frame_count} TP2.0 frame(s), {expected_len} KWP byte(s)")
                    self._last_kwp_activity_at = time.time()
                    self._last_kwp_activity_at = time.time()
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

                frame_count += 1
                self.ack_ecu_data_frame(first)
                if expected_len is not None and len(payload) >= expected_len:
                    if frame_count > 1 and self.reporter:
                        self.reporter.detail(f"Reassembled {frame_count} TP2.0 frame(s), {expected_len} KWP byte(s)")
                    return bytes(payload[:expected_len])
                continue

            if self.reporter:
                self.reporter.trace(f"Unhandled TP2.0 frame on 0x{self.tp_rx_id:03X}: {fmt(data)}")

        raise TimeoutError("Timed out waiting for KWP response")


    def drain_kwp_extras(self, quiet_timeout: float = 0.25, max_frames: int = 8) -> list[bytes]:
        """Drain extra KWP payloads that arrive after a request response.

        Some PQ35 modules answer one read-ID request with several separate KWP
        payloads. If the caller immediately sends the next request, those late
        ID payloads are mistaken for the next response and the conversation
        desynchronises. This helper consumes immediate extra application frames
        after a successful read-only preamble step. A3/Bx transport traffic is
        handled transparently by recv_kwp_response().
        """
        extras: list[bytes] = []
        for _ in range(max(0, max_frames)):
            try:
                extra = self.recv_kwp_response(
                    timeout=max(0.05, quiet_timeout),
                    control_extend=0.08,
                    max_control_extra=0.18,
                )
            except TimeoutError:
                break
            extras.append(extra)
            self._last_kwp_activity_at = time.time()
        return extras


    def channel_test(self, timeout: float = 0.4) -> bytes | None:
        """Send a tester-initiated TP2.0 A3 channel test and return A1 if seen.

        VCDS sends tester-side A3 keepalives between some non-engine requests
        before reading DTCs.  This is read-only transport housekeeping; it does
        not send a KWP diagnostic service.
        """
        self.send_can(self.tp_tx_id, [0xA3], label="CHAN-TEST")
        deadline = time.time() + timeout
        while time.time() < deadline:
            can_id, data = self.recv_can(max(0.0, deadline - time.time()))
            if can_id is None or data is None:
                break
            if can_id != self.tp_rx_id or not data:
                continue
            if data[0] == 0xA1:
                return data
            if self.handle_tp_control_frame(data):
                continue
        return None

    def idle_keepalive(self, count: int = 3, interval: float = 0.12) -> None:
        """Send a short VCDS-like run of tester A3 keepalives."""
        for _ in range(max(0, count)):
            self.channel_test(timeout=0.35)
            if interval > 0:
                time.sleep(interval)

    def _is_expected_kwp_response(self, request: bytes, resp: bytes, expected_prefixes: list[bytes] | None = None) -> bool:
        if not resp:
            return False

        if expected_prefixes:
            return any(resp.startswith(prefix) for prefix in expected_prefixes)

        # Sensible defaults for the KWP services used by this project.
        if request[:1] == b"\x10" and len(request) >= 2:
            return resp == bytes([0x50, request[1]]) or resp.startswith(b"\x7F\x10")
        if request[:1] == b"\x1A" and len(request) >= 2:
            return resp.startswith(bytes([0x5A, request[1]])) or resp.startswith(b"\x7F\x1A")
        if request[:1] == b"\x31":
            return resp.startswith(b"\x71") or resp.startswith(b"\x7F\x31")
        if request[:1] == b"\x18":
            return resp.startswith(b"\x58") or resp.startswith(b"\x7F\x18")
        if request[:1] == b"\x14":
            return resp.startswith(b"\x54") or resp.startswith(b"\x7F\x14")
        return True

    def kwp_request(
        self,
        kwp_payload: list[int] | bytes,
        timeout: float = 3.0,
        max_pending: int = 80,
        expected_prefixes: list[bytes] | None = None,
        strict_expected: bool = False,
    ) -> bytes:
        request = bytes(kwp_payload)
        self.send_tp_data(request)
        deadline = time.time() + timeout
        pending_count = 0
        discarded_count = 0

        while time.time() < deadline:
            resp = self.recv_kwp_response(timeout=max(0.1, deadline - time.time()))
            if len(resp) >= 3 and resp[0] == 0x7F and resp[2] == 0x78:
                pending_count += 1
                self.pending_response_count += 1
                if self.reporter:
                    if pending_count <= 3 or pending_count % 10 == 0:
                        self.reporter.warn(f"KWP response pending #{pending_count}: {fmt(resp)}")
                if pending_count >= max_pending:
                    raise TimeoutError(f"Too many KWP responsePending replies ({pending_count}) for request {fmt(request)}")
                # VCDS keeps waiting after every 7F xx 78. Extend the window
                # from the latest pending frame rather than from the original
                # request time.
                deadline = time.time() + timeout
                continue

            if self._is_expected_kwp_response(request, resp, expected_prefixes):
                return resp

            # A late response from the previous request is common on the body
            # and ABS modules. Do not hand stale 5A/58 fragments to the command
            # layer as if they answered the current service. ACK has already
            # happened in recv_kwp_response(), so keep waiting for the service
            # we actually asked for.
            discarded_count += 1
            if self.reporter and (discarded_count <= 3 or discarded_count % 10 == 0):
                self.reporter.warn(
                    f"Discarding stale/unexpected KWP payload while waiting for {fmt(request)}: {fmt(resp)}"
                )

            if not strict_expected:
                # Backwards-compatible path for commands that intentionally
                # accept arbitrary payloads. Module DTC/preamble requests pass
                # strict_expected=True so they get proper service matching.
                return resp

        raise TimeoutError("Timed out waiting for KWP response")
