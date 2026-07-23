"""Certificate fingerprint and STARTTLS probe helpers."""

from __future__ import annotations

import base64
import hashlib
import socket
import ssl
from typing import Any


def _fingerprint(der: bytes, algorithm: str) -> str:
    digest = hashlib.new(algorithm, der).hexdigest().upper()
    return ":".join(digest[index:index + 2] for index in range(0, len(digest), 2))


def certificate_payload(
    host: str,
    port: int,
    der: bytes,
    message: str,
    verify_code: int | None = None,
) -> dict[str, Any]:
    lower_message = message.lower()
    time_error = any(token in lower_message for token in ("expired", "not yet valid"))
    mismatch = any(token in lower_message for token in ("hostname mismatch", "not valid for"))
    return {
        "type": "CertValidationError",
        "host": host,
        "port": port,
        "message": message,
        "verifyCode": verify_code,
        "fingerprint": _fingerprint(der, "sha1"),
        "fingerprint256": _fingerprint(der, "sha256"),
        "rawDER": base64.b64encode(der).decode("ascii"),
        "isNotValidAtThisTime": time_error,
        "isDomainMismatch": mismatch,
        "isUntrusted": not time_error and not mismatch,
    }


def _read_response(socket_obj: socket.socket, limit: int = 1024 * 1024) -> bytes:
    """Read a ManageSieve response through its terminal OK/NO/BYE line."""

    data = bytearray()
    while len(data) < limit:
        chunk = socket_obj.recv(4096)
        if not chunk:
            break
        data.extend(chunk)
        for line in data.splitlines():
            upper = line.lstrip().upper()
            if upper.startswith((b"OK", b"NO", b"BYE")):
                return bytes(data)
    return bytes(data)


def probe_starttls_certificate(host: str, port: int, timeout: float) -> bytes:
    """Reconnect, issue ManageSieve STARTTLS, and retrieve the peer certificate."""

    plain = socket.create_connection((host, port), timeout=timeout)
    try:
        plain.settimeout(timeout)
        greeting = _read_response(plain)
        if not greeting:
            raise OSError("ManageSieve server did not send a greeting")

        plain.sendall(b"STARTTLS\r\n")
        response = _read_response(plain)
        terminal = response.splitlines()[-1].lstrip().upper() if response else b""
        if not terminal.startswith(b"OK"):
            raise OSError("ManageSieve server rejected STARTTLS during certificate probe")

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        tls = context.wrap_socket(plain, server_hostname=host)
        plain = None
        try:
            der = tls.getpeercert(binary_form=True)
            if not der:
                raise OSError("TLS peer did not provide a certificate")
            return der
        finally:
            tls.close()
    finally:
        if plain is not None:
            plain.close()
