from sieve_bridge.host import PROTOCOL_VERSION, SieveBridgeHost
from sieve_bridge.native_io import NativeMessagingIO
from sieve_bridge.trust_store import CertificateTrustStore


class NullIO(NativeMessagingIO):
    def __init__(self) -> None:
        self.messages = []

    def write_message(self, message):
        self.messages.append(message)


def test_hello(tmp_path) -> None:
    host = SieveBridgeHost(
        io=NullIO(),
        trust_store=CertificateTrustStore(tmp_path / "pins.json"),
    )
    result = host.dispatch({
        "version": PROTOCOL_VERSION,
        "method": "bridge.hello",
        "params": {},
    })
    assert result["protocolVersion"] == PROTOCOL_VERSION
    assert "socket.startTLS" in result["capabilities"]
