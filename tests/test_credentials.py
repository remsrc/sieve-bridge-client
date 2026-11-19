import pytest
from keyring.backends import SecretService, kwallet
from keyring.backends.chainer import ChainerBackend

from sieve_bridge.credentials import CredentialStore
from sieve_bridge.errors import BridgeError


class FakeKeyring:
    def __init__(self):
        self.values = {}

    def set_password(self, service, username, password):
        self.values[(service, username)] = password

    def get_password(self, service, username):
        return self.values.get((service, username))

    def delete_password(self, service, username):
        self.values.pop((service, username), None)


class FakeErrors:
    class PasswordDeleteError(Exception):
        pass


def make_store():
    store = CredentialStore.__new__(CredentialStore)
    store._keyring = FakeKeyring()
    store._errors = FakeErrors
    store._backend = object()
    from sieve_bridge.credentials import CredentialBackendInfo
    store._info = CredentialBackendInfo(True, True, "test.secure")
    return store


def test_credential_roundtrip():
    store = make_store()
    assert store.set("account1", "secret")["stored"] is True
    assert store.exists("account1")["exists"] is True
    assert store.get("account1")["password"] == "secret"
    assert store.delete("account1")["deleted"] is True
    assert store.exists("account1")["exists"] is False


def test_unavailable_backend_is_rejected():
    store = make_store()
    from sieve_bridge.credentials import CredentialBackendInfo
    store._info = CredentialBackendInfo(False, False, "fail", "unavailable")
    with pytest.raises(BridgeError) as exc:
        store.set("account1", "secret")
    assert exc.value.code == "CREDENTIAL_BACKEND_UNAVAILABLE"

def test_chained_backend_is_secure_when_all_contained_keyrings_are_insecure(monkeypatch : pytest.MonkeyPatch):
    monkeypatch.setattr(ChainerBackend, 'backends', [  kwallet.DBusKeyring(), SecretService.Keyring() ] )
    import keyring
    keyring.set_keyring(ChainerBackend())
    store = make_store()
    store._keyring = keyring
    actual = store._detect_backend()
    assert actual.name == "keyring.backends.chainer.ChainerBackend"
    assert actual.secure
    assert actual.available

def test_chained_backend_is_not_secure_when_one_contained_keyrings_is_insecure(monkeypatch : pytest.MonkeyPatch):
    monkeypatch.setattr(ChainerBackend, 'backends', [  FakeKeyring(), SecretService.Keyring() ] )
    import keyring
    keyring.set_keyring(ChainerBackend())
    store = make_store()
    store._keyring = keyring
    actual = store._detect_backend()
    assert actual.name == "keyring.backends.chainer.ChainerBackend"
    assert not actual.secure
    assert not actual.available
    assert actual.reason == "No supported secure operating-system credential backend is active"
