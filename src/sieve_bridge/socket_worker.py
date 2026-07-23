"""Thread-owned TCP/STARTTLS socket implementation."""

from __future__ import annotations

import base64
import hashlib
import queue
import select
import socket
import ssl
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any, Callable

from .certificates import certificate_payload, probe_starttls_certificate
from .errors import BridgeError
from .trust_store import CertificateTrustStore

EventSink = Callable[[dict[str, Any]], None]


@dataclass(slots=True)
class WorkerCommand:
    method: str
    params: dict[str, Any]
    future: Future[Any]


class SocketWorker:
    """Own exactly one socket and serialize all operations on its thread."""

    READ_CHUNK = 64 * 1024
    SELECT_INTERVAL = 0.10

    def __init__(
        self,
        socket_id: str,
        host: str,
        port: int,
        event_sink: EventSink,
        trust_store: CertificateTrustStore,
        connect_timeout: float = 15.0,
    ) -> None:
        self.socket_id = socket_id
        self.host = host
        self.port = port
        self.connect_timeout = connect_timeout
        self._event_sink = event_sink
        self._trust_store = trust_store
        self._commands: queue.Queue[WorkerCommand] = queue.Queue()
        self._socket: socket.socket | ssl.SSLSocket | None = None
        self._state = "created"
        self._stopping = False
        self._close_emitted = False
        self._thread = threading.Thread(
            target=self._run,
            name=f"sieve-socket-{socket_id}",
            daemon=True,
        )
        self._thread.start()

    def submit(self, method: str, params: dict[str, Any] | None = None) -> Future[Any]:
        future: Future[Any] = Future()
        self._commands.put(WorkerCommand(method, params or {}, future))
        return future

    def is_alive(self) -> bool:
        return self._thread.is_alive() and self._socket is not None and self._state in {"connected", "tls"}

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout)

    def _emit(self, event: str, payload: dict[str, Any] | None = None) -> None:
        self._event_sink({
            "version": 1,
            "type": "event",
            "event": event,
            "socketId": self.socket_id,
            "payload": payload or {},
        })

    def _emit_close(self, reason: str) -> None:
        if self._close_emitted:
            return
        self._close_emitted = True
        self._emit("socket.close", {"reason": reason})

    def _close_socket(self) -> None:
        current, self._socket = self._socket, None
        if current is not None:
            try:
                current.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                current.close()
            except OSError:
                pass
        self._state = "closed"

    def _connect(self) -> dict[str, Any]:
        if self._socket is not None:
            return {"state": self._state}
        try:
            current = socket.create_connection(
                (self.host, self.port),
                timeout=self.connect_timeout,
            )
            current.setblocking(False)
        except OSError as exc:
            raise BridgeError(
                "SOCKET_CONNECT_FAILED",
                f"Could not connect to {self.host}:{self.port}: {exc}",
                {"host": self.host, "port": self.port},
            ) from exc

        self._socket = current
        self._state = "connected"
        self._close_emitted = False
        return {"state": self._state}

    def _send(self, params: dict[str, Any]) -> dict[str, Any]:
        if self._socket is None:
            raise BridgeError("SOCKET_NOT_CONNECTED", "Socket is not connected")

        encoded = params.get("data")
        if not isinstance(encoded, str):
            raise BridgeError("INVALID_ARGUMENT", "send.data must be a base64 string")
        try:
            data = base64.b64decode(encoded, validate=True)
        except ValueError as exc:
            raise BridgeError("INVALID_ARGUMENT", "send.data is not valid base64") from exc

        try:
            self._socket.setblocking(True)
            self._socket.settimeout(self.connect_timeout)
            self._socket.sendall(data)
        except OSError as exc:
            self._close_socket()
            raise BridgeError("SOCKET_SEND_FAILED", f"Socket send failed: {exc}") from exc
        finally:
            if self._socket is not None:
                self._socket.settimeout(0.0)
                self._socket.setblocking(False)
        return {"bytesSent": len(data)}

    def _start_tls(self) -> dict[str, Any]:
        if self._socket is None or self._state != "connected":
            raise BridgeError("SOCKET_NOT_CONNECTED", "STARTTLS requires a plain connected socket")

        plain = self._socket
        plain.setblocking(True)
        plain.settimeout(self.connect_timeout)
        pin = self._trust_store.get_pin(self.host, self.port)

        try:
            if pin:
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            else:
                context = ssl.create_default_context()

            tls = context.wrap_socket(plain, server_hostname=self.host)
            der = tls.getpeercert(binary_form=True)
            if not der:
                tls.close()
                self._socket = None
                self._state = "closed"
                raise BridgeError("TLS_NO_CERTIFICATE", "TLS peer did not provide a certificate")

            sha256 = hashlib.sha256(der).hexdigest().lower()
            if pin and sha256 != pin.replace(":", "").lower():
                tls.close()
                self._socket = None
                self._state = "closed"
                info = certificate_payload(
                    self.host,
                    self.port,
                    der,
                    "The server certificate no longer matches the accepted certificate fingerprint.",
                )
                raise BridgeError("CERTIFICATE_CHANGED", info["message"], info)

            tls.setblocking(False)
            self._socket = tls
            self._state = "tls"
            return {
                "state": self._state,
                "fingerprint256": certificate_payload(
                    self.host, self.port, der, ""
                )["fingerprint256"],
                "pinned": bool(pin),
            }
        except ssl.SSLCertVerificationError as exc:
            self._socket = None
            self._state = "closed"
            try:
                plain.close()
            except OSError:
                pass

            try:
                der = probe_starttls_certificate(self.host, self.port, self.connect_timeout)
                info = certificate_payload(
                    self.host,
                    self.port,
                    der,
                    exc.verify_message or str(exc),
                    exc.verify_code,
                )
            except OSError:
                info = {
                    "type": "CertValidationError",
                    "host": self.host,
                    "port": self.port,
                    "message": exc.verify_message or str(exc),
                    "verifyCode": exc.verify_code,
                    "fingerprint": None,
                    "fingerprint256": None,
                    "rawDER": None,
                    "isNotValidAtThisTime": False,
                    "isDomainMismatch": "hostname mismatch" in str(exc).lower(),
                    "isUntrusted": True,
                }
            raise BridgeError("CERT_VALIDATION_FAILED", info["message"], info) from exc
        except (ssl.SSLError, OSError) as exc:
            self._socket = None
            self._state = "closed"
            try:
                plain.close()
            except OSError:
                pass
            raise BridgeError("TLS_HANDSHAKE_FAILED", f"TLS handshake failed: {exc}") from exc

    def _disconnect(self, reason: str) -> dict[str, Any]:
        self._close_socket()
        self._emit_close(reason)
        return {"state": "closed"}

    def _dispatch(self, command: WorkerCommand) -> Any:
        if command.method == "connect":
            return self._connect()
        if command.method == "send":
            return self._send(command.params)
        if command.method == "startTLS":
            return self._start_tls()
        if command.method == "isAlive":
            return {"alive": self.is_alive(), "state": self._state}
        if command.method == "disconnect":
            return self._disconnect("client-disconnect")
        if command.method == "destroy":
            self._stopping = True
            return self._disconnect("client-destroy")
        raise BridgeError("UNKNOWN_METHOD", f"Unknown socket method: {command.method}")

    def _process_commands(self) -> None:
        while True:
            try:
                command = self._commands.get_nowait()
            except queue.Empty:
                return

            try:
                result = self._dispatch(command)
            except Exception as exc:  # converted for caller, worker remains deterministic
                command.future.set_exception(exc)
            else:
                command.future.set_result(result)

    def _receive_available(self) -> None:
        current = self._socket
        if current is None:
            return
        try:
            readable, _, exceptional = select.select(
                [current], [], [current], self.SELECT_INTERVAL
            )
        except (OSError, ValueError):
            self._close_socket()
            self._emit_close("select-failed")
            return

        if exceptional:
            self._close_socket()
            self._emit_close("socket-exception")
            return
        if not readable:
            return

        try:
            data = current.recv(self.READ_CHUNK)
        except (BlockingIOError, ssl.SSLWantReadError):
            return
        except OSError as exc:
            self._close_socket()
            self._emit("socket.error", {
                "code": "SOCKET_READ_FAILED",
                "message": str(exc),
            })
            self._emit_close("read-failed")
            return

        if not data:
            self._close_socket()
            self._emit_close("remote-close")
            return

        self._emit("socket.data", {
            "data": base64.b64encode(data).decode("ascii"),
        })

    def _run(self) -> None:
        try:
            while not self._stopping:
                self._process_commands()
                self._receive_available()
                if self._socket is None:
                    time.sleep(self.SELECT_INTERVAL)
            self._process_commands()
        finally:
            self._close_socket()
