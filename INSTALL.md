# Installing SieveBridgeClient

SieveBridgeClient is a Native Messaging host used by the Sieve Reloaded Thunderbird extension. It is not a standalone desktop application and does not provide a graphical user interface.

When started directly, the program waits for framed JSON messages on standard input. This is expected behavior. Under normal operation, Thunderbird starts and stops the bridge automatically.

## Requirements

### Source installation

- Python 3.10 or later
- `pip`
- A supported operating system:
  - Windows 10/11
  - Linux
  - macOS
- Thunderbird with the Sieve Reloaded extension installed

### Binary installation

No separate Python installation is required when using a prebuilt binary.

The binary package must contain the platform-specific executable together with the supplied installation and uninstallation scripts.

---

## Installing from source

Clone or download the repository and open a terminal in the project directory containing `pyproject.toml`.

### Optional: create a virtual environment

#### Windows

```cmd
python -m venv .venv
.venv\Scripts\activate
```

#### Linux and macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Install the package

#### Windows

```cmd
python -m pip install --upgrade pip
python -m pip install .
```

#### Linux and macOS

```bash
python3 -m pip install --upgrade pip
python3 -m pip install .
```

To update an existing source installation:

#### Windows

```cmd
python -m pip install --upgrade .
```

#### Linux and macOS

```bash
python3 -m pip install --upgrade .
```

### Register the Native Messaging host

After installing the Python package, register the bridge for the current user:

#### Windows

```cmd
python -m sieve_bridge.install
```

#### Linux and macOS

```bash
python3 -m sieve_bridge.install
```

The installer creates the Native Messaging manifest and registers it in the location used by Thunderbird.

After registration, quit Thunderbird completely and start it again.

### Verify the Python installation

You can confirm that the package is importable with:

#### Windows

```cmd
python -c "import sieve_bridge; print('SieveBridgeClient is installed')"
```

#### Linux and macOS

```bash
python3 -c "import sieve_bridge; print('SieveBridgeClient is installed')"
```

Do not use a direct start of the bridge as a normal functional test. A directly started Native Messaging host waits for input on `stdin` and may appear to hang until it is terminated with `Ctrl+C`.

---

## Installing a prebuilt binary

Prebuilt packages are distributed separately for Windows, Linux, and macOS.

Before installation, place the platform-specific executable in the same directory as the provided installation script and manifest template.

## Windows

Expected package contents:

```text
SieveBridgeClient.exe
install.cmd
uninstall.cmd
de.remsrc.sieve_bridge.json
README.txt
```

### Install

1. Quit Thunderbird completely.
2. Place `SieveBridgeClient.exe` in the same folder as `install.cmd`.
3. Double-click `install.cmd`.
4. Restart Thunderbird.

The installation is performed for the current user and does not normally require administrator privileges.

The files are installed below:

```text
%LOCALAPPDATA%\SieveBridgeClient
```

The Native Messaging host is registered below:

```text
HKEY_CURRENT_USER\Software\Mozilla\NativeMessagingHosts\de.remsrc.sieve_bridge
```

### Uninstall

1. Quit Thunderbird completely.
2. Run `uninstall.cmd`.
3. Restart Thunderbird.

---

## Linux

Expected package contents:

```text
SieveBridgeClient
install.sh
uninstall.sh
de.remsrc.sieve_bridge.json.in
README.txt
```

### Install

Open a terminal in the extracted package directory and run:

```bash
chmod +x SieveBridgeClient install.sh uninstall.sh
./install.sh
```

The executable is installed to:

```text
~/.local/lib/sieve-bridge-client/SieveBridgeClient
```

The Native Messaging manifest is installed to:

```text
~/.mozilla/native-messaging-hosts/de.remsrc.sieve_bridge.json
```

Quit Thunderbird completely before installation and restart it afterwards.

### Uninstall

```bash
./uninstall.sh
```

Then restart Thunderbird.

### Credential-store note

Secure password storage on Linux requires a usable desktop credential service, such as Secret Service/libsecret or KWallet. If no supported secure backend is available, Sieve Reloaded may retain the password in its local extension storage instead.

---

## macOS

Expected package contents:

```text
SieveBridgeClient
install.command
uninstall.command
de.remsrc.sieve_bridge.json.in
README.txt
```

### Install

1. Quit Thunderbird completely.
2. Place the `SieveBridgeClient` binary in the same directory as `install.command`.
3. Double-click `install.command`.

If macOS does not allow the script to run directly, open Terminal in the package directory and run:

```bash
chmod +x SieveBridgeClient install.command uninstall.command
./install.command
```

The executable is installed to:

```text
~/Library/Application Support/SieveBridgeClient/SieveBridgeClient
```

The Thunderbird Native Messaging manifest is installed to:

```text
~/Library/Mozilla/NativeMessagingHosts/de.remsrc.sieve_bridge.json
```

Restart Thunderbird after installation.

### Uninstall

Run:

```bash
./uninstall.command
```

Then restart Thunderbird.

---

## Unsigned binaries and operating-system warnings

Prebuilt binaries may initially be distributed without a trusted code signature.

Unsigned binaries are not necessarily malicious, but the operating system cannot verify the publisher or confirm that the file has not been modified after publication. Users should download binaries only from the official project repository or its GitHub Releases page and should verify the published SHA-256 checksum where available.

### Windows

Microsoft Defender SmartScreen may display a warning such as:

```text
Windows protected your PC
```

This commonly occurs with unsigned or newly published executables that have not yet established reputation.

For test builds, the user may inspect the file properties and, after verifying the source and checksum, use the available option to run the file anyway. For normal public distribution, the executable and installer should be signed with a trusted Windows code-signing certificate.

### macOS

Gatekeeper may block an unsigned or non-notarized binary or installation script.

For test builds, the user may need to approve the file under:

```text
System Settings → Privacy & Security
```

The project should not automatically disable Gatekeeper or remove quarantine protection. For normal public distribution, the binary should be signed with an Apple Developer ID certificate and notarized by Apple.

### Linux

Linux distributions usually do not require a commercial code signature for locally installed binaries, but downloaded files may lack the executable permission. Use:

```bash
chmod +x SieveBridgeClient
```

Users should still verify the source and SHA-256 checksum before installation.

---

## Updating an existing installation

### Source installation

Update the source tree and reinstall:

#### Windows

```cmd
git pull
python -m pip install --upgrade .
python -m sieve_bridge.install
```

#### Linux and macOS

```bash
git pull
python3 -m pip install --upgrade .
python3 -m sieve_bridge.install
```

Restart Thunderbird afterwards.

### Binary installation

1. Quit Thunderbird completely.
2. Replace the old package with the new release package.
3. Run the platform-specific installation script again.
4. Restart Thunderbird.

The installer overwrites the existing executable and refreshes the Native Messaging registration.

---

## Troubleshooting

### The executable waits indefinitely when started manually

This is expected. SieveBridgeClient communicates through Native Messaging and waits for framed input from Thunderbird.

Terminate a manual test with:

```text
Ctrl+C
```

### Thunderbird reports that the Native Messaging host cannot be found

Check that:

- the installation script completed without errors,
- the Native Messaging manifest exists,
- the manifest contains the correct absolute executable path,
- the manifest name is `de.remsrc.sieve_bridge`,
- the allowed extension ID matches Sieve Reloaded,
- Thunderbird was fully restarted after installation.

### Thunderbird was running during installation

Quit Thunderbird completely, including any background process, and run the installer again.

### The password is not stored in the operating-system credential store

The bridge uses the Python `keyring` abstraction. If no supported secure backend is available, the extension can fall back to its local storage. On Linux, verify that Secret Service/libsecret or KWallet is available in the active desktop session.

---

## Security recommendations for release maintainers

Before publishing a stable end-user release:

- build each binary on its target operating system,
- publish SHA-256 checksums,
- sign Windows executables and installers,
- sign and notarize macOS binaries,
- avoid bundling development files, credentials, local manifests, or private keys,
- test installation, update, and removal on a clean user account,
- verify Native Messaging communication with the released binary rather than only with the source installation.
