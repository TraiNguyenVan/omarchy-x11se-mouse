# AI Agent Instructions for Omarchy X11SE Mouse

Guidance, architectural invariants, and safety rules for AI coding agents working on `trai.x11se-mouse`.

## Project Overview

An Omarchy bar widget and standalone CLI driver for the Attack Shark X11SE mouse, communicating via raw HID over 2.4 GHz wireless receiver or USB wired cable.

---

## Strict Hardware Safety Guardrails

When modifying driver or protocol code:

1. **No Speculative HID Writes**:
   - Never send blind, untested, or unverified byte sequences to `/dev/hidraw*`.
   - Never write to any interface other than interface 02 (`bInterfaceNumber == 02`).
2. **Mandatory Readback Verification**:
   - All setting writes (DPI, polling rate, lighting) must verify successful state application via readback before reporting success.
   - The wireless receiver may drop interrupt-endpoint ACKs (`0x50`); feature readback is the definitive source of truth.
3. **Transaction Serialization via `protocol_lock`**:
   - Run HID operations under `protocol_lock()`. Use existing helpers that acquire the lock internally and acquire it at the call site for low-level operations. Avoid nested acquisitions.
   - The lock file is `/run/user/<uid>/x11se-mouse-<uid>.lock`. If the runtime directory is absent, it falls back to `/tmp/x11se-mouse-<uid>.lock`.
   - This prevents race conditions and packet interleaving between the CLI and the background `watch` daemon running from `BarWidget.qml`.
4. **Standard Library Only**:
   - Python code must use only Python 3.10+ standard library modules (`os`, `sys`, `fcntl`, `struct`, `json`, `select`, `time`, etc.). No external pip packages.

---

## Driver & Protocol Invariants

1. **Dual Transport Identities**:
   - **Wireless Receiver**: VID `00001D57`, PID `0000FA60`, Interface `02`.
   - **Wired USB Cable**: VID `00001D57`, PID `00002125`, Interface `02`.
   - Wired mode must verify hardware identity with vendor version report `0x0B` before issuing commands.
   - Lighting control is currently verified on wireless transport only; wired returns `lighting_unsupported_transport`.
2. **Feature Read Handshake**:
   - Both transports request one-shot read permission with report `0xA0`. Use `HIDIOCGFEATURE` to read the permission response, then issue a second `HIDIOCGFEATURE` for the requested report only after permission is granted.
3. **Path & Cache Security**:
   - All file operations in `$XDG_STATE_HOME` and `$XDG_CONFIG_HOME` must use `secure_directory()` with `O_NOFOLLOW` / `dir_fd` checks to prevent symlink traversal and TOCTOU vulnerabilities.
   - State files must be created atomically via temporary files and restricted to `0o600` / `0o700`.

---

## Common Commands & Verification

Always verify changes by running the device-free unit test suite:

```sh
# Run all unit tests (must pass 100% with 0 failures)
python -m unittest discover -s tests -v

# Inspect device detection without sending HID commands
./bin/x11se-mouse devices

# Test capabilities descriptor without hardware access
./bin/x11se-mouse capabilities
```

For detailed reverse engineering offsets, report descriptor payloads, and step-by-step guidance on adding new mouse models, consult [DEVELOPING.md](DEVELOPING.md).
