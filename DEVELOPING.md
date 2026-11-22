# Developer Guide & Adding New Models

Technical reference for the X11SE hardware and protocol, with instructions for adding support for other mouse models.

## Hardware Reference (X11SE)

| Connection | VID:PID | Settings Interface | Feature Report 04 Payload |
|---|---|---|---|
| **2.4 GHz Receiver** | `1d57:fa60` | Interface 02 | 55 bytes |
| **Wired USB** | `1d57:2125` | Interface 02 | 51 bytes |
| **Bluetooth** | `045e:0007` (generic SDP) | none | not available |

- Access to interface 02 for the USB transports is granted via `udev/70-x11se-hidraw.rules`.
- Reports `05` and `0c` also differ in length between wired and wireless transports.
- Check device detection without sending commands using `./bin/x11se-mouse devices`.
- Bluetooth is matched by HID bus `0005` plus the advertised name prefix `X11SE` (observed `X11SEmouse2`), because the SDP vendor/product is the generic Microsoft `045E:0007`. Its HID report descriptor declares only input/output reports, so every vendor feature request fails with `EIO`.
- Bluetooth battery is read from the BlueZ GATT Battery Service (`bluetoothctl info <address>`). No HID node is opened, so no udev rule is required.
- Open source Linux implementation reference: [OpenSharkX11](https://github.com/clevim/OpenSharkX11).
- Proprietary Bluetooth settings operate over BlueZ GATT vendor service `FEE0`:
  - `FEE3` (`0000fee3-0000-1000-8000-00805f9b34fb`): command write channel (requires confirmed write `type='request'`).
  - `FEE4` (`0000fee4-0000-1000-8000-00805f9b34fb`): response/notification channel.
  - DPI: 56-byte Report `0x04` payload written to `FEE3`; mouse emits ACK `07 50 00 04` on `FEE4`.
  - Lighting: 15-byte Report `0x05` payload written to `FEE3`; mouse emits ACK `07 50 00 05` on `FEE4`.
  - Polling rate: BLE connection interval is hardware-fixed (~125 Hz max); polling rate writes are rejected.
- Transport precedence is wired → Bluetooth → receiver: the receiver dongle remains enumerated while the mouse is linked over Bluetooth, but denies feature reads in that state.

## Reverse Engineering Notes

Reference implementation details were extracted from official vendor software:

- **Source**: [Attack Shark X11SE Product Page](https://attackshark.com/products/attack-shark-x11se-wireless-gaming-mouse)
- **Binary**: `AttackShark.exe` (SHA-256 `e0d78c3aae2883fb3bd0e3e464d020a1f5d036b5ae9126f7c631bdefd3879daa`)
- **Key Disassembly Offsets**:
  - Read handshake: `0x424f10`
  - Model-specific callers: `0x424810`
    - Version: `0b/08` (profile 0)
    - Polling rate: `06/09` (profile 1)
    - DPI: `04/38` (profile 1)
  - DPI write call: 56 bytes at `0x4231ab` (includes bounded retries for USB stalls)
- **Prior Art**: [LinShark](https://github.com/JSjuan/LinShark) documents related wired transactions for the X8 Pro.

## Adding Another Mouse Model

When adding support for a new model:

1. **Identify Hardware**:
   - Determine USB vendor/product IDs and the dedicated settings interface.
   - Inspect HID report descriptors across both wired and wireless receiver connections.
   - Never assume similar model names share the same protocol or packet layout.

2. **Verify on Hardware**:
   - Verify battery event reports, supported polling rates, and valid DPI steps on physical hardware.
   - Test read and write transactions safely, ensuring settings can be read back and restored.

3. **Code Changes**:
   - Register the identity in `model_catalog.py` with its verified capabilities and asset mappings.
   - Route discovery in `hid_discovery.py` to the appropriate model handler.
   - Implement or adapt protocol logic in `x11se_mouse.py` (or a dedicated protocol module).
   - Ensure transactions remain serialized and verified via readback.

4. **Testing**:
   - Add unit tests with recorded or mocked packets under `tests/`.
   - Run the test suite:
     ```sh
     python -m unittest discover -s tests -v
     ```
