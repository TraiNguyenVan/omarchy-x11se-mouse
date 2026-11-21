# Omarchy X11SE Mouse

An Omarchy bar widget and standalone CLI for the Attack Shark X11SE, connected by USB cable or its 2.4 GHz receiver. Click the mouse icon to open the settings panel and check battery, DPI and polling rate. Use Refresh in the panel to check again.

**Requirements:** Omarchy Quattro, Python 3.10 or newer (standard library only), and an X11SE connected by USB or its 2.4 GHz receiver. Other Attack Shark models are not currently supported.

![X11SE mouse settings panel with battery, DPI presets and polling-rate controls](preview.png)

## Install

Install the plugin from Omarchy:

```sh
omarchy plugin add https://github.com/TraiNguyenVan/omarchy-x11se-mouse.git --enable
```

Install the udev rule and reconnect the mouse or receiver:

```sh
sudo ~/.config/omarchy/plugins/trai.x11se-mouse/scripts/install-udev-rule.sh
```

## Remove

```sh
omarchy plugin remove trai.x11se-mouse
sudo rm -f /etc/udev/rules.d/70-x11se-hidraw.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw
```

## CLI

A standalone CLI is available in `./bin/x11se-mouse`:

```sh
./bin/x11se-mouse status
./bin/x11se-mouse set-dpi 800
./bin/x11se-mouse set-polling 500
./bin/x11se-mouse --help
```

## Development

Run the device-free protocol and CLI tests with:

```sh
python -m unittest discover -s tests -v
```

See [DEVELOPING.md](DEVELOPING.md) for the model boundary and the evidence needed to add another mouse.

## License

MIT. See [LICENSE](LICENSE).
