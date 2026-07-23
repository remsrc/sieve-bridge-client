"""Secure operating-system credential storage for Sieve Reloaded."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import BridgeError

SERVICE_NAME = "Sieve Reloaded"


@dataclass(frozen=True, slots=True)
class CredentialBackendInfo:
    available: bool
    secure: bool
    name: str
    reason: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "secure": self.secure,
            "backend": self.name,
            "reason": self.reason,
        }


class CredentialStore:
    """Wrap Python keyring and reject unsafe or unavailable backends."""

    def __init__(self) -> None:
        self._keyring = None
        self._errors = None
        self._backend = None
        self._info = self._detect_backend()

    @staticmethod
    def _is_secure_backend(backend: Any) -> bool:
        identity = (
            f"{backend.__class__.__module__}.{backend.__class__.__name__}"
        ).lower()

        insecure_markers = (
            "keyring.backends.fail",
            "keyring.backends.null",
            "keyrings.alt.file",
            "plaintext",
            "encryptedkeyring",
        )
        if any(marker in identity for marker in insecure_markers):
            return False

        secure_markers = (
            "keyring.backends.windows",
            "keyring.backends.macos",
            "keyring.backends.secretservice",
            "keyring.backends.libsecret",
            "kwallet",
        )
        return any(marker in identity for marker in secure_markers)

    @staticmethod
    def _backend_name(backend: Any) -> str:
        return f"{backend.__class__.__module__}.{backend.__class__.__name__}"

    def _detect_backend(self) -> CredentialBackendInfo:
        try:
            import keyring
            import keyring.errors
        except Exception as exc:
            return CredentialBackendInfo(
                available=False,
                secure=False,
                name="unavailable",
                reason=f"Python keyring is unavailable: {exc}",
            )

        self._keyring = keyring
        self._errors = keyring.errors

        try:
            backend = keyring.get_keyring()
        except Exception as exc:
            return CredentialBackendInfo(
                available=False,
                secure=False,
                name="unavailable",
                reason=f"Credential backend could not be initialized: {exc}",
            )

        self._backend = backend
        name = self._backend_name(backend)
        secure = self._is_secure_backend(backend)
        if not secure:
            return CredentialBackendInfo(
                available=False,
                secure=False,
                name=name,
                reason="No supported secure operating-system credential backend is active",
            )

        return CredentialBackendInfo(
            available=True,
            secure=True,
            name=name,
        )

    def backend(self) -> dict[str, Any]:
        return self._info.to_payload()

    def _require_available(self) -> None:
        if not self._info.available or not self._info.secure:
            raise BridgeError(
                "CREDENTIAL_BACKEND_UNAVAILABLE",
                self._info.reason or "Secure credential storage is unavailable",
                self._info.to_payload(),
            )

    @staticmethod
    def _validate_id(credential_id: Any) -> str:
        if not isinstance(credential_id, str) or not credential_id.strip():
            raise BridgeError(
                "INVALID_ARGUMENT",
                "credentialId must be a non-empty string",
            )
        if len(credential_id) > 512:
            raise BridgeError(
                "INVALID_ARGUMENT",
                "credentialId is too long",
            )
        return credential_id.strip()

    def set(self, credential_id: Any, password: Any) -> dict[str, Any]:
        self._require_available()
        credential_id = self._validate_id(credential_id)
        if not isinstance(password, str) or not password:
            raise BridgeError(
                "INVALID_ARGUMENT",
                "password must be a non-empty string",
            )
        try:
            self._keyring.set_password(SERVICE_NAME, credential_id, password)
        except Exception as exc:
            raise BridgeError(
                "CREDENTIAL_STORE_FAILED",
                f"Could not store credential: {exc}",
                self._info.to_payload(),
            ) from exc
        return {"stored": True, **self._info.to_payload()}

    def get(self, credential_id: Any) -> dict[str, Any]:
        self._require_available()
        credential_id = self._validate_id(credential_id)
        try:
            password = self._keyring.get_password(SERVICE_NAME, credential_id)
        except Exception as exc:
            raise BridgeError(
                "CREDENTIAL_READ_FAILED",
                f"Could not read credential: {exc}",
                self._info.to_payload(),
            ) from exc
        return {
            "found": password is not None,
            "password": password if password is not None else "",
            **self._info.to_payload(),
        }

    def exists(self, credential_id: Any) -> dict[str, Any]:
        result = self.get(credential_id)
        result.pop("password", None)
        return {"exists": result.pop("found"), **result}

    def delete(self, credential_id: Any) -> dict[str, Any]:
        self._require_available()
        credential_id = self._validate_id(credential_id)
        try:
            self._keyring.delete_password(SERVICE_NAME, credential_id)
        except self._errors.PasswordDeleteError:
            return {"deleted": False, **self._info.to_payload()}
        except Exception as exc:
            raise BridgeError(
                "CREDENTIAL_DELETE_FAILED",
                f"Could not delete credential: {exc}",
                self._info.to_payload(),
            ) from exc
        return {"deleted": True, **self._info.to_payload()}
