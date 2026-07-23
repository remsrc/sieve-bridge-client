"""Firefox/Thunderbird Native Messaging framing."""

from __future__ import annotations

import json
import struct
import sys
import threading
from typing import Any, BinaryIO

from .errors import BridgeError

_HEADER = struct.Struct("@I")
_MAX_INBOUND_BYTES = 16 * 1024 * 1024


class NativeMessagingIO:
    """Read and write length-prefixed UTF-8 JSON messages."""

    def __init__(
        self,
        stdin: BinaryIO | None = None,
        stdout: BinaryIO | None = None,
    ) -> None:
        self._stdin = stdin or sys.stdin.buffer
        self._stdout = stdout or sys.stdout.buffer
        self._write_lock = threading.Lock()

    @staticmethod
    def _read_exact(stream: BinaryIO, length: int) -> bytes:
        chunks: list[bytes] = []
        remaining = length
        while remaining:
            chunk = stream.read(remaining)
            if not chunk:
                raise EOFError("Native Messaging stream ended unexpectedly")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def read_message(self) -> dict[str, Any] | None:
        raw_length = self._stdin.read(_HEADER.size)
        if raw_length == b"":
            return None
        if len(raw_length) != _HEADER.size:
            raise EOFError("Incomplete Native Messaging message header")

        (length,) = _HEADER.unpack(raw_length)
        if length > _MAX_INBOUND_BYTES:
            raise BridgeError(
                "MESSAGE_TOO_LARGE",
                f"Inbound Native Messaging message exceeds {_MAX_INBOUND_BYTES} bytes",
                {"length": length},
            )

        payload = self._read_exact(self._stdin, length)
        message = json.loads(payload.decode("utf-8"))
        if not isinstance(message, dict):
            raise BridgeError("INVALID_MESSAGE", "Native message must be a JSON object")
        return message

    def write_message(self, message: dict[str, Any]) -> None:
        payload = json.dumps(
            message,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

        with self._write_lock:
            self._stdout.write(_HEADER.pack(len(payload)))
            self._stdout.write(payload)
            self._stdout.flush()
