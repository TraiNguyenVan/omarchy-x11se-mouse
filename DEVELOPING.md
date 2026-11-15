# Adding another mouse

Only the X11SE 2.4 GHz receiver is currently supported. `model_catalog.py` describes its verified USB identity and UI choices; `hid_discovery.py` matches registered identities, and `x11se_mouse.py` implements the X11SE protocol. The CLI exposes the descriptor with `capabilities` and keeps the existing status and tuning interface.

Before adding a model, identify its USB vendor, product and settings interface and verify its HID reports, permissions, battery events, DPI values and polling rates on that hardware. Do not assume a similar name means a compatible protocol. Add a separate protocol implementation where necessary, register its exact identity, route discovery and CLI operations to it, and supply only verified capabilities and suitable assets. Model selection, separate per-device state, permissions and multi-device behavior need explicit design and testing when a second model is added; the current CLI selects only X11SE.

Preserve serialized transactions, readback verification, actionable errors, and existing user settings. Add protocol and discovery tests with recorded or mocked data, then verify reads and carefully test writes on the actual receiver. `python -m unittest discover -s tests -v` runs the device-free tests.
