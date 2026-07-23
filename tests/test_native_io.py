from __future__ import annotations

import io
import json
import struct

from sieve_bridge.native_io import NativeMessagingIO


def frame(message: dict) -> bytes:
    payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
    return struct.pack("@I", len(payload)) + payload


def test_read_and_write_roundtrip() -> None:
    source = io.BytesIO(frame({"version": 1, "id": "1", "method": "bridge.hello"}))
    target = io.BytesIO()
    native = NativeMessagingIO(source, target)

    assert native.read_message()["method"] == "bridge.hello"
    native.write_message({"ok": True, "value": "ä"})

    target.seek(0)
    (length,) = struct.unpack("@I", target.read(4))
    payload = json.loads(target.read(length).decode("utf-8"))
    assert payload == {"ok": True, "value": "ä"}
