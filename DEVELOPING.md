# Developer Guide & Adding New Models

Technical reference for the X11SE hardware and protocol, with instructions for adding support for other mouse models.

## Hardware Reference (X11SE)

| Connection | VID:PID | Settings Interface | Feature Report 04 Payload |
|---|---|---|---|
| **2.4 GHz Receiver** | `1d57:fa60` | Interface 02 | 55 bytes |
| **Wired USB** | `1d57:2125` | Interface 02 | 51 bytes |

- Access to interface 02 for both transports is granted via `udev/70-x11se-hidraw.rules`.
- Reports `05` and `0c` also differ in length between wired and wireless transports.
- Check device detection without sending commands using `./bin/x11se-mouse devices`.

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
