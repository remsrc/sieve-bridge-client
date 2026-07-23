"""Register the Native Messaging host for the current user."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys
from pathlib import Path

from .host import HOST_NAME

ADDON_ID = "sieve.remsrc@mozdev.org"


def _application_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "SieveBridge"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "SieveBridge"
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "sievebridge"


def _manifest_path() -> Path:
    filename = f"{HOST_NAME}.json"
    if sys.platform == "darwin":
        # Thunderbird's documented per-user path differs from Firefox's.
        return Path.home() / "Library" / "Mozilla" / "NativeMessagingHosts" / filename
    if sys.platform == "linux":
        return Path.home() / ".mozilla" / "native-messaging-hosts" / filename
    return _application_dir() / filename


def _write_launcher(app_dir: Path) -> Path:
    app_dir.mkdir(parents=True, exist_ok=True)
    if getattr(sys, "frozen", False):
        source = Path(sys.executable).resolve()
        target = app_dir / source.name
        if source != target:
            shutil.copy2(source, target)
        return target

    if sys.platform == "win32":
        launcher = app_dir / "sieve-bridge-host.cmd"
        launcher.write_text(
            f'@echo off\r\n"{sys.executable}" -u -m sieve_bridge\r\n',
            encoding="utf-8",
        )
        return launcher

    launcher = app_dir / "sieve-bridge-host"
    launcher.write_text(
        f"#!/bin/sh\nexec {json.dumps(sys.executable)} -u -m sieve_bridge\n",
        encoding="utf-8",
    )
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
    return launcher


def install() -> tuple[Path, Path]:
    app_dir = _application_dir()
    launcher = _write_launcher(app_dir)
    manifest = {
        "name": HOST_NAME,
        "description": "Native Messaging transport for Sieve Reloaded",
        "path": str(launcher.resolve()),
        "type": "stdio",
        "allowed_extensions": [ADDON_ID],
    }

    manifest_path = _manifest_path()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if sys.platform == "win32":
        import winreg

        key_path = rf"Software\Mozilla\NativeMessagingHosts\{HOST_NAME}"
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, None, 0, winreg.REG_SZ, str(manifest_path.resolve()))

    return launcher, manifest_path


def uninstall() -> None:
    manifest_path = _manifest_path()
    try:
        manifest_path.unlink()
    except FileNotFoundError:
        pass

    if sys.platform == "win32":
        import winreg

        key_path = rf"Software\Mozilla\NativeMessagingHosts\{HOST_NAME}"
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", choices=("install", "uninstall"), default="install")
    args = parser.parse_args()

    if args.action == "uninstall":
        uninstall()
        print("Sieve Bridge Native Messaging host removed.")
        return 0

    launcher, manifest = install()
    print(f"Launcher: {launcher}")
    print(f"Manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
