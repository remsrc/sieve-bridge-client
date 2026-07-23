from pathlib import Path

from sieve_bridge.trust_store import CertificateTrustStore


def test_store_roundtrip(tmp_path: Path) -> None:
    store = CertificateTrustStore(tmp_path / "pins.json")
    fingerprint = "AA:" + "11:" * 30 + "BB"
    normalized = fingerprint.replace(":", "").lower()
    assert len(normalized) == 64

    store.trust("Mail.Example.org", 4190, fingerprint)
    assert store.get_pin("mail.example.org", 4190) == normalized
    assert store.remove("mail.example.org", 4190) is True
    assert store.get_pin("mail.example.org", 4190) is None
