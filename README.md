# Omarchy X11SE Mouse

An Omarchy bar widget and standalone CLI for the Attack Shark X11SE 2.4 GHz receiver. Hover over the mouse icon for battery, DPI and polling-rate status; click it to open the settings panel.

**Requirements:** Omarchy Quattro, Python 3.10 or newer (standard library only), and the X11SE 2.4 GHz receiver. Other Attack Shark models are not currently supported.

![X11SE mouse settings panel with battery, DPI presets and polling-rate controls](assets/x11se-current-panel.png)

## Install

Install the plugin from Omarchy:

```sh
omarchy plugin add https://github.com/TraiNguyenVan/omarchy-x11se-mouse.git --enable
```

The receiver exposes its settings through `hidraw` interface 02 (USB VID:PID `1d57:fa60`). Install the matching udev rule and grant your account access to the `input` group with one sudo authorization:

```sh
sudo ~/.config/omarchy/plugins/trai.x11se-mouse/scripts/install-udev-rule.sh
```

Reconnect the receiver after setup. If the script adds your account to `input`, log out and back in for the new group membership to take effect. The plugin itself does not use sudo; normal status reads and settings changes run as your user.

## Remove

Remove the plugin and its device rule:

```sh
omarchy plugin remove trai.x11se-mouse
sudo rm /etc/udev/rules.d/99-x11se-hidraw.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw
```

If setup added your account to the `input` group and you no longer need that membership for other devices, remove it with `sudo gpasswd -d "$USER" input`, then log out and back in.

## Using the panel

Click the mouse icon in the bar to open the panel. Select a DPI preset or polling rate to change the mouse setting. The dashed outline indicates a change is being applied; the filled button shows the last known or confirmed setting. Use **Refresh** to read current settings from the receiver.

The default DPI presets are 400, 800, 1,600, 2,400, 3,200, 5,000 and 22,000. Click the underlined **DPI PRESET** label to choose seven different values for the preset board. Saving the board does not change the current DPI. Presets are saved in `${XDG_CONFIG_HOME:-~/.config}/omarchy/x11se-presets.json`.

The DPI dropdown contains 33 values confirmed by receiver readback during testing; it is not a complete scan of the mouse’s supported range. The preset editor also includes the seven defaults. Available polling rates are 125, 250, 500 and 1,000 Hz.

Hover over the mouse illustration to reveal six clickable appearance choices. These change the illustration manually; the plugin does not detect the physical mouse color.

The bar’s watcher listens for battery events without periodically polling settings. Some displayed values can be cached; use **Refresh** to request current settings.

## CLI

Run the CLI from the plugin directory, `~/.config/omarchy/plugins/trai.x11se-mouse`. Device commands require the receiver permission described above.

```sh
./bin/x11se-mouse status
./bin/x11se-mouse status --json
./bin/x11se-mouse set-dpi 800
./bin/x11se-mouse set-polling 500
./bin/x11se-mouse capabilities
```

The bar starts `watch` automatically. Run `./bin/x11se-mouse watch` to inspect its JSON event stream, or add `--debug` to a device command for Python tracebacks. `capabilities` prints the X11SE model descriptor without accessing the receiver. Run `./bin/x11se-mouse --help` for all options.

DPI and polling changes are checked using receiver readback. If an acknowledgement is missing but readback confirms the requested setting, the CLI reports success with a warning; mismatches and failed readbacks are reported as errors.

## Development

Run the device-free protocol and CLI tests with:

```sh
python -m unittest discover -s tests -v
```

See [DEVELOPING.md](DEVELOPING.md) for the model boundary and the evidence needed to add another mouse.

## License

MIT. See [LICENSE](LICENSE).
