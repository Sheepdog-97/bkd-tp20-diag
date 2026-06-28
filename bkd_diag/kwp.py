from __future__ import annotations

NEGATIVE_RESPONSE_CODES = {
    0x10: "generalReject",
    0x11: "serviceNotSupported",
    0x12: "subFunctionNotSupported",
    0x21: "busyRepeatRequest",
    0x22: "conditionsNotCorrect",
    0x31: "requestOutOfRange",
    0x33: "securityAccessDenied",
    0x35: "invalidKey",
    0x36: "exceedNumberOfAttempts",
    0x37: "requiredTimeDelayNotExpired",
    0x78: "responsePending",
}


def decode_negative(resp: bytes) -> tuple[int, int, str] | None:
    if len(resp) >= 3 and resp[0] == 0x7F:
        svc = resp[1]
        code = resp[2]
        return svc, code, NEGATIVE_RESPONSE_CODES.get(code, "unknown")
    return None
