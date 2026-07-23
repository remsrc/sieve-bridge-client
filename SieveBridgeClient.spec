# -*- mode: python ; coding: utf-8 -*-

"""
Cross-platform PyInstaller specification for SieveBridgeClient.

Build from the repository root with:

    python -m PyInstaller --clean --noconfirm SieveBridgeClient.spec

PyInstaller must still be executed separately on each target operating system.
The same specification can be used on Windows, Linux, and macOS.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules


PROJECT_ROOT = Path(SPECPATH).resolve()
SOURCE_ROOT = PROJECT_ROOT / "src"
ENTRY_POINT = PROJECT_ROOT / "sieve_bridge_launcher.py"

if not ENTRY_POINT.is_file():
    raise FileNotFoundError(f"PyInstaller entry point not found: {ENTRY_POINT}")

if not SOURCE_ROOT.is_dir():
    raise FileNotFoundError(f"Python source directory not found: {SOURCE_ROOT}")


# keyring loads operating-system-specific backends dynamically. Collecting all
# package data and backend modules ensures that the relevant backend is present
# in the executable built on each target platform.
keyring_datas, keyring_binaries, keyring_hiddenimports = collect_all("keyring")
keyring_hiddenimports += collect_submodules("keyring.backends")
keyring_hiddenimports = sorted(set(keyring_hiddenimports))


a = Analysis(
    [str(ENTRY_POINT)],
    pathex=[str(SOURCE_ROOT)],
    binaries=keyring_binaries,
    datas=keyring_datas,
    hiddenimports=keyring_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="SieveBridgeClient",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX is intentionally disabled for reproducibility and to avoid
    # platform-specific compression and signing issues.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    # Native Messaging uses stdin/stdout. A console build is required so that
    # these streams remain available, including on Windows.
    console=True,
    disable_windowed_traceback=False,
    # argv emulation is unnecessary for a Native Messaging host.
    argv_emulation=False,
    target_arch=None,
    # macOS signing can be supplied later in a dedicated release/signing step.
    codesign_identity=None,
    entitlements_file=None,
)
