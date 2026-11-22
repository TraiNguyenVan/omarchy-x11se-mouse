# AI Agent Instructions for Omarchy X11SE Mouse

Guidance, safety rules, and protocol invariants for AI coding agents working on `trai.x11se-mouse`. Edit this file but never bloat it; keep under 100 lines.

Purpose: Omarchy bar widget and standalone CLI driver for the Attack Shark X11SE mouse. Raw HID over 2.4 GHz receiver or USB cable; Bluetooth battery status via BlueZ and GATT settings writes (DPI/lighting) with FEE4 notification readback.

## Hardware Safety Guardrails

1. **No speculative HID writes**: never send blind or unverified byte sequences to `/dev/hidraw*`; never write to any USB interface other than interface 02 (`bInterfaceNumber == 02`); never send vendor feature writes over Bluetooth (kernel returns `EIO`).
2. **Mandatory readback verification**: all setting writes (DPI, polling rate, lighting) must verify state via readback before reporting success. Feature readback is the definitive source of truth.
3. **Transaction serialization via `protocol_lock`**: run HID operations under `protocol_lock()`; lock file is `/run/user/<uid>/x11se-mouse-<uid>.lock`, falling back to `/tmp/x11se-mouse-<uid>.lock`. Prevents races between CLI and background `watch`.
4. **Standard library only**: Python 3.10+ stdlib only; no external pip packages.

## Protocol & Hardware Invariants

1. **Transports**: wireless receiver VID `00001D57` PID `0000FA60` interface 02; wired USB VID `00001D57` PID `00002125` interface 02; Bluetooth HID bus `0005`, name prefix `X11SE` (SDP `045E:0007` is generic). Precedence: wired → Bluetooth → receiver.
2. **Wired**: verify hardware identity with vendor version report `0x0B` before commands. Lighting on wired returns `lighting_unsupported_transport` (verified on receiver only).
3. **Bluetooth**: battery from BlueZ GATT Battery Service (`bluetoothctl info <address>`). Settings writes (DPI, lighting) route via GATT vendor service FEE0 (FEE3 request, FEE4 ACK notification verification). Polling rate fixed ~125 Hz, rejected with `bluetooth_polling_unsupported`. No hidraw for Bluetooth settings.
4. **Feature read handshake**: request one-shot read permission with report `0xA0` via `HIDIOCGFEATURE`, then read the requested report with a second `HIDIOCGFEATURE` only after permission granted.
5. **Path & cache security**: `$XDG_STATE_HOME` / `$XDG_CONFIG_HOME` file ops use `secure_directory()` (`O_NOFOLLOW` / `dir_fd` checks); state files created atomically via temp files, `0o600` / `0o700`.

## Verification

Run the device-free unit test suite (must pass 100%, 0 failures):

```sh
python -m unittest discover -s tests -v
./bin/x11se-mouse devices      # device detection, no HID commands
./bin/x11se-mouse capabilities   # capabilities descriptor, no hardware access
```

New-model guidance: see DEVELOPING.md.
