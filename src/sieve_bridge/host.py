"""Native Messaging host and request dispatcher."""

from __future__ import annotations

import logging
import sys
import threading
import uuid
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any

from . import __version__
from .credentials import CredentialStore
from .errors import BridgeError
from .native_io import NativeMessagingIO
from .socket_worker import SocketWorker
from .trust_store import CertificateTrustStore

HOST_NAME = "de.remsrc.sieve_bridge"
PROTOCOL_VERSION = 1
REQUEST_TIMEOUT = 30.0


def _configure_logging() -> None:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


class SieveBridgeHost:
    """Multiplex Native Messaging requests over multiple TCP workers."""

    def __init__(
        self,
        io: NativeMessagingIO | None = None,
        trust_store: CertificateTrustStore | None = None,
        credential_store: CredentialStore | None = None,
    ) -> None:
        self.io = io or NativeMessagingIO()
        self.trust_store = trust_store or CertificateTrustStore()
        self.credential_store = credential_store or CredentialStore()
        self._workers: dict[str, SocketWorker] = {}
        self._lock = threading.RLock()

    def _send_event(self, message: dict[str, Any]) -> None:
        self.io.write_message(message)

    @staticmethod
    def _require_params(message: dict[str, Any]) -> dict[str, Any]:
        params = message.get("params", {})
        if not isinstance(params, dict):
            raise BridgeError("INVALID_ARGUMENT", "params must be an object")
        return params

    def _worker(self, socket_id: str) -> SocketWorker:
        with self._lock:
            worker = self._workers.get(socket_id)
        if worker is None:
            raise BridgeError("UNKNOWN_SOCKET", f"Unknown socket id: {socket_id}")
        return worker

    def _socket_create(self, params: dict[str, Any]) -> dict[str, Any]:
        host = params.get("host")
        port = params.get("port")
        timeout_ms = params.get("connectTimeoutMs", 15000)
        if not isinstance(host, str) or not host.strip():
            raise BridgeError("INVALID_ARGUMENT", "host must be a non-empty string")
        try:
            port = int(port)
            timeout = max(1.0, min(float(timeout_ms) / 1000.0, 120.0))
        except (TypeError, ValueError) as exc:
            raise BridgeError("INVALID_ARGUMENT", "port and timeout must be numeric") from exc
        if not 1 <= port <= 65535:
            raise BridgeError("INVALID_ARGUMENT", "port must be between 1 and 65535")

        socket_id = uuid.uuid4().hex
        worker = SocketWorker(
            socket_id,
            host.strip(),
            port,
            self._send_event,
            self.trust_store,
            timeout,
        )
        with self._lock:
            self._workers[socket_id] = worker
        return {"socketId": socket_id}

    def _socket_call(self, method: str, params: dict[str, Any]) -> Any:
        socket_id = params.get("socketId")
        if not isinstance(socket_id, str):
            raise BridgeError("INVALID_ARGUMENT", "socketId must be a string")
        worker = self._worker(socket_id)
        future = worker.submit(method, params)
        try:
            result = future.result(timeout=REQUEST_TIMEOUT)
        except FutureTimeoutError as exc:
            raise BridgeError("REQUEST_TIMEOUT", f"Socket operation {method} timed out") from exc

        if method == "destroy":
            with self._lock:
                self._workers.pop(socket_id, None)
            worker.join(1.0)
        return result

    def _certificate_trust(self, params: dict[str, Any]) -> dict[str, Any]:
        host = params.get("host")
        port = params.get("port")
        fingerprint = params.get("fingerprint256")
        if not isinstance(host, str) or not isinstance(fingerprint, str):
            raise BridgeError(
                "INVALID_ARGUMENT",
                "host and fingerprint256 must be strings",
            )
        try:
            port = int(port)
            self.trust_store.trust(host, port, fingerprint)
        except (TypeError, ValueError) as exc:
            raise BridgeError("INVALID_ARGUMENT", str(exc)) from exc
        return {"trusted": True}

    def _certificate_remove(self, params: dict[str, Any]) -> dict[str, Any]:
        host = params.get("host")
        try:
            port = int(params.get("port"))
        except (TypeError, ValueError) as exc:
            raise BridgeError("INVALID_ARGUMENT", "port must be numeric") from exc
        if not isinstance(host, str):
            raise BridgeError("INVALID_ARGUMENT", "host must be a string")
        return {"removed": self.trust_store.remove(host, port)}

    def dispatch(self, message: dict[str, Any]) -> Any:
        version = message.get("version")
        if version != PROTOCOL_VERSION:
            raise BridgeError(
                "UNSUPPORTED_PROTOCOL",
                f"Unsupported bridge protocol version: {version}",
                {"supported": PROTOCOL_VERSION},
            )

        method = message.get("method")
        if not isinstance(method, str):
            raise BridgeError("INVALID_MESSAGE", "method must be a string")
        params = self._require_params(message)

        if method == "bridge.hello":
            return {
                "name": HOST_NAME,
                "hostVersion": __version__,
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": [
                    "socket.connect",
                    "socket.startTLS",
                    "socket.send",
                    "certificate.pin.sha256",
                    "credential.backend",
                    "credential.set",
                    "credential.get",
                    "credential.exists",
                    "credential.delete",
                ],
            }
        if method == "socket.create":
            return self._socket_create(params)
        if method.startswith("socket."):
            operation = method.split(".", 1)[1]
            return self._socket_call(operation, params)
        if method == "certificate.trust":
            return self._certificate_trust(params)
        if method == "certificate.remove":
            return self._certificate_remove(params)
        if method == "credential.backend":
            return self.credential_store.backend()
        if method == "credential.set":
            return self.credential_store.set(
                params.get("credentialId"), params.get("password")
            )
        if method == "credential.get":
            return self.credential_store.get(params.get("credentialId"))
        if method == "credential.exists":
            return self.credential_store.exists(params.get("credentialId"))
        if method == "credential.delete":
            return self.credential_store.delete(params.get("credentialId"))
        raise BridgeError("UNKNOWN_METHOD", f"Unknown bridge method: {method}")

    def close(self) -> None:
        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
        for worker in workers:
            try:
                worker.submit("destroy").result(timeout=2.0)
            except Exception:
                pass
            worker.join(1.0)

    def run(self) -> int:
        try:
            while True:
                message = self.io.read_message()
                if message is None:
                    return 0

                request_id = message.get("id")
                if not isinstance(request_id, str):
                    self.io.write_message({
                        "version": PROTOCOL_VERSION,
                        "type": "response",
                        "id": None,
                        "ok": False,
                        "error": BridgeError(
                            "INVALID_MESSAGE", "id must be a string"
                        ).to_payload(),
                    })
                    continue

                try:
                    result = self.dispatch(message)
                except BridgeError as exc:
                    response = {
                        "version": PROTOCOL_VERSION,
                        "type": "response",
                        "id": request_id,
                        "ok": False,
                        "error": exc.to_payload(),
                    }
                except Exception as exc:
                    logging.exception("Unhandled bridge request error")
                    response = {
                        "version": PROTOCOL_VERSION,
                        "type": "response",
                        "id": request_id,
                        "ok": False,
                        "error": {
                            "code": "INTERNAL_ERROR",
                            "message": str(exc),
                            "details": {},
                        },
                    }
                else:
                    response = {
                        "version": PROTOCOL_VERSION,
                        "type": "response",
                        "id": request_id,
                        "ok": True,
                        "result": result,
                    }
                self.io.write_message(response)
        finally:
            self.close()


def main() -> int:
    _configure_logging()
    return SieveBridgeHost().run()


if __name__ == "__main__":
    raise SystemExit(main())
