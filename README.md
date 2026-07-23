# SieveBridgeClient

Initial transport implementation for replacing Sieve Reloaded's Thunderbird `SieveSocketApi` Experiment with a persistent Native Messaging host.

## Scope of this first implementation

- Native Messaging framing over `stdin` / `stdout`
- Versioned request/response/event protocol
- Multiple concurrent ManageSieve TCP sockets
- Explicit STARTTLS upgrade
- Default operating-system CA validation through Python/OpenSSL
- SHA-256 certificate pinning after a user-approved certificate exception
- Per-user host registration for Windows, Linux and macOS
- JavaScript `SieveBridgeClient` and replacement `SieveClient.mjs`

The existing ManageSieve request, response, session and parser classes remain unchanged.

## Native protocol

Requests:

```json
{
  "version": 1,
  "type": "request",
  "id": "request-id",
  "method": "socket.create",
  "params": {"host": "sieve.example.org", "port": 4190}
}
```

Responses use the same `id`. Socket data and close notifications are emitted as independent `event` messages. Binary data is Base64 encoded. Python limits each received TCP chunk to 64 KiB, keeping host-to-extension Native Messaging messages well below Mozilla's 1 MiB limit.

## Development installation

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -e .
sieve-bridge-install install
```

Add `nativeMessaging` to the add-on permissions and copy:

- `addon/SieveBridgeClient.mjs` to `libs/libManageSieve/SieveBridgeClient.mjs`
- `addon/SieveClient.mjs` to `libs/libManageSieve/SieveClient.mjs`

The production distribution should provide a signed/packaged executable per operating system, so end users do not need a separate Python installation.

## Certificate exception model

A normal STARTTLS handshake uses the system trust store and hostname verification. If validation fails, the bridge reconnects only to retrieve the STARTTLS certificate and returns SHA-1/SHA-256 fingerprints plus the DER certificate. After explicit approval, the SHA-256 fingerprint is stored per host and port. Future connections use an unverified TLS handshake but accept it only when the exact certificate fingerprint matches the stored pin.

## Deliberately not included yet

- Replacement for `SieveAccountsApi` password access
- Replacement for `SieveMenuApi`
- Graphical installer and release packaging
- Automated migration of existing Thunderbird certificate overrides

## Credential storage (0.2.0)

The bridge exposes `credential.backend`, `credential.set`, `credential.get`,
`credential.exists`, and `credential.delete`. It uses Python `keyring` and only
accepts supported secure operating-system backends. If no secure backend is
available, the bridge returns `CREDENTIAL_BACKEND_UNAVAILABLE`; the extension
may then retain its local compatibility storage.

After upgrading an existing Python installation, register the Python launcher
again so the Native Messaging manifest no longer points to an older frozen
installer executable:

```text
python -m pip install --upgrade .
python -m sieve_bridge.install
```
