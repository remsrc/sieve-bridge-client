"""Persistent SHA-256 certificate pin store."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any


class CertificateTrustStore:
    """Store certificate pins per host and port in the user's profile."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or self.default_path()
        self._lock = threading.RLock()

    @staticmethod
    def default_path() -> Path:
        if sys.platform == "win32":
            base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
            return base / "SieveBridge" / "trusted_certificates.json"
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "SieveBridge" / "trusted_certificates.json"
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return base / "sievebridge" / "trusted_certificates.json"

    @staticmethod
    def _key(host: str, port: int) -> str:
        return f"{host.lower()}:{port}"

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"version": 1, "pins": {}}
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "pins": {}}

        if not isinstance(data, dict) or not isinstance(data.get("pins"), dict):
            return {"version": 1, "pins": {}}
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix="trusted_certificates.",
            suffix=".tmp",
            dir=self.path.parent,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.write("\n")
            os.replace(temporary, self.path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    def get_pin(self, host: str, port: int) -> str | None:
        with self._lock:
            entry = self._load()["pins"].get(self._key(host, port))
            if not isinstance(entry, dict):
                return None
            value = entry.get("sha256")
            return value if isinstance(value, str) else None

    def trust(self, host: str, port: int, sha256: str) -> None:
        normalized = sha256.replace(":", "").lower()
        if len(normalized) != 64 or any(c not in "0123456789abcdef" for c in normalized):
            raise ValueError("Invalid SHA-256 certificate fingerprint")

        with self._lock:
            data = self._load()
            data["pins"][self._key(host, port)] = {"sha256": normalized}
            self._save(data)

    def remove(self, host: str, port: int) -> bool:
        with self._lock:
            data = self._load()
            removed = data["pins"].pop(self._key(host, port), None) is not None
            if removed:
                self._save(data)
            return removed
