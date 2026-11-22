"""Verified model identity and UI capabilities; no HID access occurs here."""

# Identity observed on the directly connected X11SE; its protocol is unverified.
X11SE_WIRED = {
    "id": "x11se-wired",
    "usb": {"vendor": "00001D57", "product": "00002125", "interface": "02"},
}

# Bluetooth HID advertises generic SDP (045E:0007); proprietary settings
# operate over vendor GATT FEE0 (FEE3 write request / FEE4 notify ACK).
X11SE_BLUETOOTH = {
    "id": "x11se-bluetooth",
    "name": "Attack Shark X11SE",
    "bluetooth": {"bus": "0005", "name": "X11SE"},
    "controls": ["battery", "dpi", "lighting"],
}

X11SE = {
    "id": "x11se",
    "name": "Attack Shark X11SE",
    "usb": {"vendor": "00001D57", "product": "0000FA60", "interface": "02"},
    "controls": ["battery", "dpi", "polling"],
    "defaultPresets": [400, 800, 1600, 2400, 3200, 5000, 22000],
    "verifiedDpi": [50, 100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600,
                    650, 700, 750, 800, 850, 900, 950, 1000, 1050, 1100, 1150,
                    1200, 1250, 1300, 1350, 1750, 9950, 12100, 19900, 20200, 22000],
    "pollingRates": [125, 250, 500, 1000],
    "maxReportedDpi": 26000,
    "stageCount": 8,
    "appearances": [
        {"name": "white", "color": "#f4f3ee", "asset": "assets/mice/white.png"},
        {"name": "white-line", "color": "#c7c7c2", "asset": "assets/mice/white-line.png"},
        {"name": "black", "color": "#202127", "asset": "assets/mice/black.png"},
        {"name": "black-line", "color": "#55565e", "asset": "assets/mice/black-line.png"},
        {"name": "red", "color": "#d63b39", "asset": "assets/mice/red.png"},
        {"name": "berry-red", "color": "#9d344e", "asset": "assets/mice/berry-red.png"},
    ],
}
