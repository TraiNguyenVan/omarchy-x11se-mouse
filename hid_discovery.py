"""Discover hidraw interfaces by explicitly registered USB or Bluetooth identity."""
import glob
import os
import re

USB_BUS = "0003"
BLUETOOTH_BUS = "0005"
BLUETOOTH_ADDRESS = re.compile(r"^[0-9a-f]{2}(?::[0-9a-f]{2}){5}$")


def _read_uevent(sys_path):
    identity = ""
    name = ""
    with open(os.path.join(sys_path, "device", "uevent"), encoding="ascii") as stream:
        for line in stream:
            if line.startswith("HID_ID="):
                identity = line[7:].strip()
            elif line.startswith("HID_NAME="):
                name = line[9:].strip()
    return identity, name


def _usb_interface(sys_path):
    device_path = os.path.realpath(os.path.join(sys_path, "device"))
    with open(os.path.join(os.path.dirname(device_path), "bInterfaceNumber"), encoding="ascii") as stream:
        return stream.read().strip().lower().zfill(2)


def find_hidraw(models, errors):
    errors.clear()
    for sys_path in sorted(glob.glob('/sys/class/hidraw/hidraw*')):
        try:
            identity, name = _read_uevent(sys_path)
            if not identity:
                continue
            bus = identity.split(":", 1)[0]
            device_path = '/dev/' + os.path.basename(sys_path)
            for model in models:
                usb = model.get("usb")
                if usb:
                    if identity != f"{USB_BUS}:{usb['vendor']}:{usb['product']}":
                        continue
                    if _usb_interface(sys_path) != usb["interface"].lower().zfill(2):
                        continue
                    return model, device_path
                bluetooth = model.get("bluetooth")
                if bluetooth:
                    # Bluetooth HID has no USB interface number; the advertised
                    # HID name is the stable identity across adapters and firmware.
                    if bus != bluetooth.get("bus", BLUETOOTH_BUS):
                        continue
                    if not name.lower().startswith(bluetooth["name"].lower()):
                        continue
                    return model, device_path
        except (OSError, UnicodeError, ValueError) as error:
            errors.append({'path': sys_path, 'error': str(error)})
    return None


def hid_identity(device):
    """Return the kernel HID identity of a hidraw device without opening it."""
    node = os.path.basename(os.path.realpath(device))
    if not node.startswith("hidraw"):
        return None
    try:
        with open(os.path.join("/sys/class/hidraw", node, "device", "uevent"), encoding="ascii") as stream:
            fields = {}
            for line in stream:
                key, separator, value = line.partition("=")
                if separator and key in ("HID_ID", "HID_NAME", "HID_UNIQ"):
                    fields[key] = value.strip()
    except (OSError, UnicodeError):
        return None
    parts = fields.get("HID_ID", "").split(":")
    if len(parts) != 3:
        return None
    return {"bus": parts[0], "vendor": parts[1], "product": parts[2],
            "name": fields.get("HID_NAME", ""), "uniq": fields.get("HID_UNIQ", "")}


def bluetooth_address(device):
    """Return the lower-case Bluetooth address reported by the kernel, if any."""
    identity = hid_identity(device)
    if not identity or identity["bus"] != BLUETOOTH_BUS:
        return None
    address = identity["uniq"].lower()
    return address if BLUETOOTH_ADDRESS.match(address) else None
