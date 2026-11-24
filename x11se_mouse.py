"""X11SE receiver protocol and HID access. Importable without a device for tests."""
from __future__ import annotations

import array
import contextlib
import errno
import fcntl
import json
import os
import re
import select
import struct
import subprocess
import time
from typing import Any

import hid_discovery
from model_catalog import X11SE, X11SE_BLUETOOTH, X11SE_WIRED

VENDOR_ID = X11SE["usb"]["vendor"]
PRODUCT_ID = X11SE["usb"]["product"]
INTERFACE = X11SE["usb"]["interface"]
DPI_REPORT = 0x04
POLLING_REPORT = 0x06
READ_PERMISSION_REPORT = 0xA0
POLLING_CODES = {125: 0x08, 250: 0x04, 500: 0x02, 1000: 0x01}
CODE_POLLING = {value: key for key, value in POLLING_CODES.items()}
COMMON_DPI_PRESETS = tuple(X11SE["defaultPresets"])
WRITES_ENABLED = True
CACHE_WARNINGS: list[dict[str, str]] = []
DISCOVERY_ERRORS: list[dict[str, str]] = []
BLUETOOTH_BATTERY_POLL_SECONDS = 30.0
BLUETOOTH_BATTERY_PATTERN = re.compile(
    r"^\s*Battery Percentage:\s+0x[0-9a-fA-F]+\s+\((\d{1,3})\)\s*$", re.MULTILINE)

# PixArt PAW3311 encoding table used by the X11/X11SE receiver protocol.
DPI_TABLE = [
    0x01,0x02,0x03,0x04,0x05,0x06,0x08,0x09,0x0a,0x0b,0x0c,0x0e,0x0f,0x10,0x11,0x12,0x13,0x15,0x16,
    0x17,0x18,0x19,0x1b,0x1c,0x1d,0x1e,0x1f,0x20,0x22,0x23,0x24,0x25,0x26,0x27,0x29,0x2a,0x2b,0x2c,
    0x2d,0x2f,0x30,0x31,0x32,0x33,0x34,0x36,0x37,0x38,0x39,0x3a,0x3b,0x3d,0x3e,0x3f,0x40,0x41,0x43,
    0x44,0x45,0x46,0x47,0x48,0x4a,0x4b,0x4c,0x4d,0x4e,0x4f,0x51,0x52,0x53,0x54,0x55,0x57,0x58,0x59,
    0x5a,0x5b,0x5c,0x5e,0x5f,0x60,0x61,0x62,0x63,0x65,0x66,0x67,0x68,0x69,0x6b,0x6c,0x6d,0x6e,0x6f,
    0x70,0x72,0x73,0x74,0x75,0x76,0x77,0x79,0x7a,0x7b,0x7c,0x7d,0x7f,0x80,0x81,0x82,0x83,0x84,0x86,
    0x87,0x88,0x89,0x8a,0x8b,0x8d,0x8e,0x8f,0x90,0x91,0x93,0x94,0x95,0x96,0x97,0x98,0x9a,0x9b,0x9c,
    0x9d,0x9e,0x9f,0xa1,0xa2,0xa3,0xa4,0xa5,0xa7,0xa8,0xa9,0xaa,0xab,0xac,0xae,0xaf,0xb0,0xb1,0xb2,
    0xb3,0xb5,0xb6,0xb7,0xb8,0xb9,0xbb,0xbc,0xbd,0xbe,0xbf,0xc0,0xc2,0xc3,0xc4,0xc5,0xc6,0xc7,0xc9,
    0xca,0xcb,0xcc,0xcd,0xcf,0xd0,0xd1,0xd2,0xd3,0xd4,0xd6,0xd7,0xd8,0xd9,0xda,0xdb,0xdd,0xde,0xdf,
    0xe0,0xe1,0xe3,0xe4,0xe5,0xe6,0xe7,0xe8,0xea,0xeb,0x76,0x77,0x79,0x7a,0x7b,0x7c,0x7d,0x7f,0x80,
    0x81,0x82,0x83,0x84,0x86,0x87,0x88,0x89,0x8a,0x8b,0x8d,
]


class MouseError(RuntimeError):
    """Device discovery, permission, or protocol error suitable for CLI output."""

    def __init__(self, message: str, *, code: str = "mouse_error", operation: str | None = None,
                 details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.operation = operation
        self.details = details or {}


@contextlib.contextmanager
def protocol_lock():
    """Serialize receiver transactions across the bar watcher and CLI calls."""
    runtime_dir = f"/run/user/{os.getuid()}"
    if not os.path.isdir(runtime_dir):
        runtime_dir = "/tmp"
    lock_path = os.path.join(runtime_dir, f"x11se-mouse-{os.getuid()}.lock")
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def ioctl_number(direction: int, number: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (ord("H") << 8) | number


def find_hidraw() -> str | None:
    # A wired cable and an active Bluetooth HID node both prove the mouse is
    # linked. The receiver dongle stays enumerated even when the mouse is in
    # Bluetooth mode, so it is only used when neither active link exists.
    DISCOVERY_ERRORS.clear()
    wired = hid_discovery.find_hidraw((X11SE_WIRED,), [])
    if wired:
        return wired[1]
    bluetooth_errors: list[dict[str, str]] = []
    bluetooth = hid_discovery.find_hidraw((X11SE_BLUETOOTH,), bluetooth_errors)
    if bluetooth:
        return bluetooth[1]
    DISCOVERY_ERRORS.extend(bluetooth_errors)
    receiver_errors: list[dict[str, str]] = []
    match = hid_discovery.find_hidraw((X11SE,), receiver_errors)
    DISCOVERY_ERRORS.extend(receiver_errors)
    return match[1] if match else None


def is_wired(path: str) -> bool:
    wired = hid_discovery.find_hidraw((X11SE_WIRED,), [])
    return bool(wired and os.path.realpath(path) == os.path.realpath(wired[1]))


def is_bluetooth(path: str) -> bool:
    identity = hid_discovery.hid_identity(path)
    return bool(identity and identity["bus"] == hid_discovery.BLUETOOTH_BUS
                and identity["name"].lower().startswith(X11SE_BLUETOOTH["bluetooth"]["name"].lower()))


def open_device(device: str | None = None) -> tuple[int, str]:
    path = device or find_hidraw()
    if not path:
        raise MouseError("X11SE mouse was not found over USB, its 2.4 GHz receiver, or Bluetooth",
                         code="mouse_not_found", operation="open_device",
                         details={"discovery_errors": DISCOVERY_ERRORS[:]})
    try:
        return os.open(path, os.O_RDWR | os.O_NONBLOCK), path
    except PermissionError as error:
        raise MouseError(f"Permission denied opening {path}; check the X11SE hidraw rule",
                         code="permission_denied", operation="open_device",
                         details={"device": path, "errno": error.errno}) from error
    except OSError as error:
        raise MouseError(f"Could not open {path}: {error.strerror}", code="device_open_failed",
                         operation="open_device", details={"device": path, "errno": error.errno}) from error


def parse_bluetooth_battery(output: str) -> int | None:
    match = BLUETOOTH_BATTERY_PATTERN.search(output or "")
    if not match:
        return None
    value = int(match.group(1))
    return value if 0 <= value <= 100 else None


def bluetooth_battery(address: str | None) -> int | None:
    """Read the GATT Battery Service level through BlueZ; never touches HID."""
    if not address:
        return None
    try:
        completed = subprocess.run(
            ["bluetoothctl", "info", address],
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            timeout=3, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_bluetooth_battery(completed.stdout)


def bluetooth_status(device: str) -> dict[str, Any]:
    address = hid_discovery.bluetooth_address(device)
    return {
        "connected": True,
        "transport": "bluetooth",
        "battery": bluetooth_battery(address),
        "chargeState": None,
        "dpi": None,
        "stage": None,
        "stages": None,
        "polling": None,
        "settingsAvailable": True,
        "error": None,
    }


def bluetooth_polling_unsupported_error() -> MouseError:
    return MouseError(
        "Polling rate cannot be configured over Bluetooth (hardware fixed to 125 Hz); "
        "connect the 2.4 GHz receiver or the USB cable",
        code="bluetooth_polling_unsupported", operation="bluetooth_settings")


def bluetooth_settings_error() -> MouseError:
    return bluetooth_polling_unsupported_error()


def bluetooth_gatt_paths(address: str) -> tuple[str, str] | None:
    dev_str = "dev_" + address.upper().replace(":", "_")
    try:
        proc = subprocess.run(["busctl", "tree", "org.bluez"], capture_output=True, text=True, check=False)
        tree = proc.stdout
    except OSError:
        return None
    char_paths = [
        line.strip().split()[-1]
        for line in tree.splitlines()
        if dev_str in line and "/char" in line and "/desc" not in line
    ]
    fee3 = None
    fee4 = None
    for cp in char_paths:
        try:
            res = subprocess.run(
                ["busctl", "get-property", "org.bluez", cp, "org.bluez.GattCharacteristic1", "UUID"],
                capture_output=True, text=True, check=False
            )
            val = res.stdout.lower()
            if "fee3" in val:
                fee3 = cp
            elif "fee4" in val:
                fee4 = cp
        except OSError:
            continue
    if fee3 and fee4:
        return fee3, fee4
    return None


def bluetooth_gatt_write_and_verify(address: str, payload: bytes | bytearray, expected_report_id: int, timeout: float = 3.0) -> bool:
    paths = bluetooth_gatt_paths(address)
    if not paths:
        raise MouseError("Bluetooth GATT service FEE0 characteristics not found", code="bluetooth_gatt_unavailable")
    fee3_path, fee4_path = paths

    try:
        mon = subprocess.Popen([
            "dbus-monitor", "--system",
            f"type='signal',interface='org.freedesktop.DBus.Properties',path='{fee4_path}'"
        ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    except OSError as error:
        raise MouseError(f"Failed to start dbus-monitor: {error}", code="bluetooth_monitor_failed") from error

    try:
        time.sleep(0.15)
        try:
            ctl = subprocess.Popen(["bluetoothctl"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        except OSError as error:
            raise MouseError(f"Failed to start bluetoothctl: {error}", code="bluetoothctl_failed") from error

        hex_bytes = " ".join(f"0x{b:02x}" for b in payload)
        script = (
            "menu gatt\n"
            f"select-attribute {fee4_path}\n"
            "notify on\n"
            f"select-attribute {fee3_path}\n"
            f'write "{hex_bytes}" 0 request\n'
        )
        ctl.stdin.write(script)
        ctl.stdin.flush()

        start = time.time()
        buf = ""
        ack_seen = False

        fl = fcntl.fcntl(mon.stdout.fileno(), fcntl.F_GETFL)
        fcntl.fcntl(mon.stdout.fileno(), fcntl.F_SETFL, fl | os.O_NONBLOCK)

        expected_ack_pat = re.compile(rf"(?:07|55)\s+50\s+00\s+{expected_report_id:02x}")

        while time.time() - start < timeout:
            try:
                chunk = mon.stdout.read()
                if chunk:
                    buf += chunk
                    if expected_ack_pat.search(buf):
                        ack_seen = True
                        break
            except (BlockingIOError, IOError):
                pass
            time.sleep(0.05)

        try:
            ctl.stdin.write("notify off\nexit\n")
            ctl.stdin.flush()
            ctl.communicate(timeout=0.5)
        except Exception:
            ctl.kill()

        if not ack_seen:
            raise MouseError(f"Bluetooth setting write for report 0x{expected_report_id:02x} could not be confirmed by readback ACK",
                             code="bluetooth_write_unverified", operation="bluetooth_gatt_write",
                             details={"report_id": f"0x{expected_report_id:02x}"})
        return True
    finally:
        mon.terminate()
        try:
            mon.communicate(timeout=0.5)
        except Exception:
            mon.kill()


def bluetooth_build_dpi_report(value: int, cached: dict | None = None) -> tuple[bytearray, int, list[int]]:
    stages = list((cached and cached.get("stages")) or [400, 800, 1600, 2400, 3200, 5000])
    while len(stages) < 6:
        stages.append(1000)
    stages = stages[:6]

    stage = (cached and cached.get("stage")) or 2
    if not (1 <= stage <= 6):
        stage = 2
    stages[stage - 1] = value

    buf = bytearray(56)
    buf[0] = 0x04
    buf[1] = 0x38
    buf[2] = 0x01
    buf[5] = 0x3f
    for i, d in enumerate(stages):
        xb, yb, dbl, trp = encode_dpi(d)
        buf[8 + i] = xb
        buf[16 + i] = yb
        if dbl:
            buf[6] |= (1 << i)
        if trp:
            buf[7] |= (1 << i)
    buf[24] = stage
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 255)]
    for i, (r, g, b) in enumerate(colors):
        buf[25 + i * 3] = r
        buf[26 + i * 3] = g
        buf[27 + i * 3] = b
    buf[49] = 0x00
    struct.pack_into(">H", buf, 50, sum(buf[3:50]))
    return buf, stage, stages


def bluetooth_set_dpi(device: str, value: int, cached: dict | None = None) -> dict[str, Any]:
    address = hid_discovery.bluetooth_address(device)
    if not address:
        raise MouseError("Bluetooth address could not be resolved", code="bluetooth_address_missing")
    report, stage, stages = bluetooth_build_dpi_report(value, cached)
    with protocol_lock():
        bluetooth_gatt_write_and_verify(address, report, DPI_REPORT)
    return {
        "dpi": value,
        "stage": stage,
        "stages": stages,
        "verified": True,
        "acknowledged": True,
    }


def bluetooth_build_lighting_report(color: str | None = None, power: str | None = None, cached: dict | None = None) -> bytearray:
    buf = bytearray(15)
    buf[0] = 0x05
    buf[1] = 0x0f
    buf[2] = 0x01
    current_power = power or (cached and cached.get("lightPower")) or "on"
    buf[3] = 0x10 if current_power == "on" else 0x00
    buf[4] = 0x03
    buf[5] = 0xa8
    hex_col = color or (cached and cached.get("lightColor")) or "#00ff00"
    if hex_col.startswith("#"):
        hex_col = hex_col[1:]
    rgb = bytes.fromhex(hex_col)
    buf[6:9] = rgb
    buf[9] = 0x01
    buf[10] = 0x04
    buf[11:13] = sum(buf[3:11]).to_bytes(2, "big")
    return buf


def bluetooth_set_lighting_color(device: str, color: str, cached: dict | None = None) -> dict[str, Any]:
    if len(color) != 7 or color[0] != "#" or any(c not in "0123456789abcdefABCDEF" for c in color[1:]):
        raise ValueError("LED color must be a six-digit hexadecimal color")
    address = hid_discovery.bluetooth_address(device)
    if not address:
        raise MouseError("Bluetooth address could not be resolved", code="bluetooth_address_missing")
    report = bluetooth_build_lighting_report(color=color, cached=cached)
    with protocol_lock():
        bluetooth_gatt_write_and_verify(address, report, 0x05)
    return {"color": color.lower(), "verified": True}


def bluetooth_set_lighting_power(device: str, power: str, cached: dict | None = None) -> dict[str, Any]:
    if power not in ("on", "off"):
        raise ValueError("LED power must be on or off")
    address = hid_discovery.bluetooth_address(device)
    if not address:
        raise MouseError("Bluetooth address could not be resolved", code="bluetooth_address_missing")
    report = bluetooth_build_lighting_report(power=power, cached=cached)
    with protocol_lock():
        bluetooth_gatt_write_and_verify(address, report, 0x05)
    return {"power": power, "verified": True}


def bluetooth_set_polling(device: str, rate: int) -> dict[str, Any]:
    raise bluetooth_polling_unsupported_error()


def send_feature(fd: int, report: bytes | bytearray) -> None:
    buffer = bytearray(report)
    try:
        fcntl.ioctl(fd, ioctl_number(3, 0x06, len(buffer)), buffer, True)
    except OSError as error:
        raise MouseError(f"HID feature write failed: {error.strerror}", code="hid_feature_write_failed",
                         operation="send_feature",
                         details={"report_id": f"0x{buffer[0]:02x}" if buffer else None,
                                  "errno": error.errno}) from error


def read_feature(fd: int, report_id: int, length: int, profile: int = 1) -> bytearray:
    # The receiver grants a one-shot read before each feature report request.
    permission = bytearray([READ_PERMISSION_REPORT, report_id, length, 0, profile, 0, 0, 0])
    send_feature(fd, permission)
    time.sleep(0.25)
    permission_response = bytearray(8)
    permission_response[0] = READ_PERMISSION_REPORT
    try:
        fcntl.ioctl(fd, ioctl_number(3, 0x07, len(permission_response)), permission_response, True)
    except OSError as error:
        raise MouseError(f"HID read-permission check failed: {error.strerror}",
                         code="hid_permission_check_failed", operation="read_feature",
                         details={"report_id": f"0x{report_id:02x}", "errno": error.errno}) from error
    if permission_response[1] != 1:
        raise MouseError(f"Receiver denied read permission for report 0x{report_id:02x}",
                         code="hid_read_denied", operation="read_feature",
                         details={"report_id": f"0x{report_id:02x}",
                                  "permission_status": permission_response[1]})
    report = bytearray(length)
    report[0] = report_id
    try:
        fcntl.ioctl(fd, ioctl_number(3, 0x07, len(report)), report, True)
    except OSError as error:
        raise MouseError(f"HID feature read failed: {error.strerror}", code="hid_feature_read_failed",
                         operation="read_feature",
                         details={"report_id": f"0x{report_id:02x}", "errno": error.errno}) from error
    return report


def read_wired_feature(fd: int, report_id: int, length: int, profile: int = 1) -> bytearray:
    # The vendor retries stalled read requests; never retry settings writes here.
    for attempt in range(5):
        try:
            report = read_feature(fd, report_id, length, profile)
            if (report[0] != report_id or report[1] != length or
                    (report_id == 0x0b and report[3] != 7) or
                    (report_id != 0x0b and report[2] != profile)):
                raise MouseError("Unexpected wired feature report", code="invalid_wired_report")
            return report
        except MouseError as error:
            if (error.details.get("errno") != errno.EPIPE and error.code != "invalid_wired_report") or attempt == 4:
                raise
            time.sleep(0.5)


def read_receiver_feature(fd: int, report_id: int, length: int) -> bytearray:
    # The receiver may briefly deny reads immediately after switching from USB.
    for attempt in range(3):
        try:
            return read_feature(fd, report_id, length)
        except MouseError as error:
            if error.code != "hid_read_denied" or attempt == 2:
                raise
            time.sleep(0.5)


def read_lighting(fd: int) -> bytearray:
    report = read_receiver_feature(fd, 0x05, 15)
    if (report[:3] != bytes((5, 15, 1)) or
            int.from_bytes(report[11:13], "big") != sum(report[3:11])):
        raise MouseError("Invalid lighting report", code="invalid_lighting_report")
    return report


def lighting_color(report: bytes | bytearray) -> str:
    return "#" + bytes(report[6:9]).hex()


def lighting_power(report: bytes | bytearray) -> str:
    return {0: "off", 1: "on"}.get(report[3] >> 4, "unsupported")


def write_lighting(fd: int, report: bytearray) -> bytearray:
    report[11:13] = sum(report[3:11]).to_bytes(2, "big")
    send_feature(fd, report)
    for attempt in range(3):
        time.sleep(0.5)
        try:
            actual = read_lighting(fd)
            if actual[:13] == report[:13]:
                return actual
        except MouseError as error:
            if error.code not in ("invalid_lighting_report", "hid_read_denied"):
                raise
    raise MouseError("Lighting change could not be confirmed by readback", code="lighting_write_unverified")

def set_lighting_color(fd: int, color: str) -> dict[str, Any]:
    if len(color) != 7 or color[0] != "#" or any(c not in "0123456789abcdefABCDEF" for c in color[1:]):
        raise ValueError("LED color must be a six-digit hexadecimal color")
    with protocol_lock():
        report = read_lighting(fd)
        report[6:9] = bytes.fromhex(color[1:])
        actual = write_lighting(fd, report)
        return {"color": lighting_color(actual), "verified": True}


def set_lighting_power(fd: int, power: str) -> dict[str, Any]:
    if power not in ("on", "off"):
        raise ValueError("LED power must be on or off")
    with protocol_lock():
        report = read_lighting(fd)
        # On forces Static. Off only clears the effect nibble, so it can leave an unknown effect.
        if power == "on" and lighting_power(report) == "unsupported":
            raise MouseError("The current lighting effect is not supported", code="lighting_effect_unsupported")
        report[3] = (report[3] & 0x0f) | (0x10 if power == "on" else 0)
        actual = write_lighting(fd, report)
        return {"power": lighting_power(actual), "verified": True}


def wired_status(fd: int) -> dict[str, Any]:
    with protocol_lock():
        version = read_wired_feature(fd, 0x0b, 8, 0)
        if version[3] != 7:
            raise MouseError("Wired device did not identify as an X11SE", code="unexpected_wired_model")
        polling_report = read_wired_feature(fd, POLLING_REPORT, 9)
        dpi_report = read_wired_feature(fd, DPI_REPORT, 56)
    dpi = decode_dpi_report(dpi_report)
    polling = decode_polling_report(polling_report)
    if dpi is None or polling is None or polling_report[4] != (~polling_report[3] & 0xff):
        raise MouseError("Invalid wired settings report", code="invalid_wired_report")
    return {"connected": True, "transport": "wired", "battery": None, "chargeState": None,
            "polling": polling, "error": None, **dpi}


def set_wired(fd: int, name: str, value: int) -> dict[str, Any]:
    with protocol_lock():
        version = read_wired_feature(fd, 0x0b, 8, 0)
        if version[3] != 7:
            raise MouseError("Wired device did not identify as an X11SE", code="unexpected_wired_model")
        report_id, length = (DPI_REPORT, 56) if name == "set-dpi" else (POLLING_REPORT, 9)
        if report_id == DPI_REPORT:
            report = update_dpi_report(read_wired_feature(fd, report_id, length), value)
        else:
            report = encode_polling_report(value)
        for attempt in range(5):
            try:
                send_feature(fd, report)
                break
            except MouseError as error:
                if error.details.get("errno") != errno.EPIPE or attempt == 4:
                    raise
                time.sleep(0.5)
        for attempt in range(5):
            time.sleep(0.5)
            try:
                readback = read_wired_feature(fd, report_id, length)
                if report_id == DPI_REPORT:
                    result = decode_dpi_report(readback)
                    if result and result["dpi"] == value:
                        return {**result, "verified": True, "acknowledged": False}
                elif decode_polling_report(readback) == value and readback[4] == (~readback[3] & 0xff):
                    return {"polling": value, "verified": True, "acknowledged": False}
            except MouseError as error:
                if error.code not in ("invalid_wired_report", "hid_read_denied") and error.details.get("errno") != errno.EPIPE:
                    raise
        raise MouseError("Wired setting could not be confirmed by readback", code="wired_write_unverified")


def valid_dpi_report(report: bytes | bytearray) -> bool:
    return len(report) == 56 and struct.unpack_from(">H", report, 50)[0] == sum(report[3:50])


def encode_dpi(value: int) -> tuple[int, int, bool, bool]:
    """Return (x byte, y byte, double flag, triple flag) for a supported DPI."""
    if not isinstance(value, int) or value < 50 or value > 22000:
        raise ValueError("DPI must be an integer from 50 to 22000")
    if 10000 < value <= 12000:
        raise ValueError("DPI values from 10050 to 12000 are unsupported by this receiver")

    doubled = value > 12000
    encoded = round(value / 2) if doubled else value
    if encoded <= 10000:
        encoded = max(50, round(encoded / 50) * 50)
        index = (encoded - 50) // 50
        y_byte = 0
    else:
        encoded = max(10100, round(encoded / 100) * 100)
        index = 200 + (encoded - 10100) // 100
        y_byte = 1
    if index < 0 or index >= len(DPI_TABLE):
        raise ValueError("DPI value cannot be represented by the X11SE sensor")
    return DPI_TABLE[index], y_byte, doubled, False


def _matching_indices(byte_value: int) -> list[int]:
    return [index for index, value in enumerate(DPI_TABLE) if value == byte_value]


def decode_dpi_value(x_byte: int, y_byte: int, double_flag: bool, triple_flag: bool) -> int | None:
    if x_byte == 0 and y_byte == 0:
        return None
    indices = _matching_indices(x_byte)
    if not indices:
        return None
    index = indices[-1] if double_flag or triple_flag else indices[0]
    if y_byte == 0:
        dpi = index * 50 + 50
    elif y_byte == 1:
        dpi = 10100 + (index - 200) * 100 if index >= 200 else index * 100 + 100
    else:
        return None
    if double_flag:
        dpi *= 2
    if triple_flag:
        dpi *= 3
    return dpi if 0 < dpi <= 26000 else None


def decode_dpi_report(report: bytes | bytearray) -> dict[str, Any] | None:
    if not valid_dpi_report(report):
        return None
    stage = report[24]
    if not 1 <= stage <= 8:
        return None
    stages: list[int | None] = []
    for index in range(8):
        stages.append(decode_dpi_value(
            report[8 + index], report[16 + index],
            bool(report[6] & (1 << index)), bool(report[7] & (1 << index)),
        ))
    return {"stage": stage, "dpi": stages[stage - 1], "stages": stages}


def update_dpi_report(report: bytes | bytearray, dpi: int) -> bytearray:
    if not valid_dpi_report(report):
        raise MouseError("Receiver returned an invalid DPI report checksum", code="invalid_dpi_report",
                         operation="decode_dpi_report", details={"report_id": f"0x{DPI_REPORT:02x}"})
    stage = report[24]
    if not 1 <= stage <= 8:
        raise MouseError("Receiver returned an invalid active DPI stage", code="invalid_dpi_stage",
                         operation="decode_dpi_report", details={"stage": stage})
    x_byte, y_byte, double_flag, triple_flag = encode_dpi(dpi)
    updated = bytearray(report)
    index = stage - 1
    updated[8 + index] = x_byte
    updated[16 + index] = y_byte
    updated[6] = (updated[6] | (1 << index)) if double_flag else (updated[6] & ~(1 << index))
    updated[7] = (updated[7] | (1 << index)) if triple_flag else (updated[7] & ~(1 << index))
    struct.pack_into(">H", updated, 50, sum(updated[3:50]))
    return updated


def encode_polling_report(rate: int, profile: int = 1) -> bytearray:
    if rate not in POLLING_CODES:
        raise ValueError("Polling rate must be one of 125, 250, 500, or 1000")
    code = POLLING_CODES[rate]
    return bytearray([POLLING_REPORT, 0x09, profile, code, code ^ 0xFF, 0, 0, 0, 0])


def decode_polling_report(report: bytes | bytearray) -> int | None:
    if len(report) < 5:
        return None
    return CODE_POLLING.get(report[3])


def parse_event(data: bytes) -> dict[str, Any] | None:
    if len(data) != 5 or data[2] not in (0x40, 0x41) or data[4] > 100:
        return None
    state = {1: "normal", 2: "charged", 3: "charging"}.get(data[3])
    return {"battery": data[4], "chargeState": state} if state else None


def parse_command_confirmation(data: bytes, expected_report: int) -> int | None:
    if len(data) != 5 or data[2] != 0x50 or data[4] != expected_report or data[3] not in (0, 1):
        return None
    return data[3]


def wait_for_command_confirmation(
    fd: int,
    report_id: int,
    current: dict[str, Any] | None = None,
    timeout: float = 1.5,
) -> None:
    """Wait for the receiver's input-endpoint ACK before issuing another feature request."""
    events = current if current is not None else {}
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise MouseError(f"Receiver did not acknowledge report 0x{report_id:02x}",
                             code="ack_timeout", operation="wait_for_command_confirmation",
                             details={"report_id": f"0x{report_id:02x}", "timeout_seconds": timeout})
        try:
            ready, _, _ = select.select([fd], [], [], remaining)
        except OSError as error:
            raise MouseError(f"Could not wait for receiver confirmation: {error.strerror}",
                             code="confirmation_wait_failed", operation="wait_for_command_confirmation",
                             details={"report_id": f"0x{report_id:02x}", "errno": error.errno}) from error
        if not ready:
            raise MouseError(f"Receiver did not acknowledge report 0x{report_id:02x}",
                             code="ack_timeout", operation="wait_for_command_confirmation",
                             details={"report_id": f"0x{report_id:02x}", "timeout_seconds": timeout})
        try:
            data = os.read(fd, 128)
        except BlockingIOError:
            continue
        except OSError as error:
            raise MouseError(f"Could not read receiver confirmation: {error.strerror}",
                             code="confirmation_read_failed", operation="wait_for_command_confirmation",
                             details={"report_id": f"0x{report_id:02x}", "errno": error.errno}) from error
        battery = parse_event(data)
        if battery:
            events.update(battery)
            continue
        confirmation = parse_command_confirmation(data, report_id)
        if confirmation is None:
            continue
        if confirmation == 1:
            raise MouseError(f"Receiver rejected report 0x{report_id:02x}", code="ack_rejected",
                             operation="wait_for_command_confirmation",
                             details={"report_id": f"0x{report_id:02x}"})
        return


def drain_events(fd: int, current: dict[str, Any], timeout: float = 0) -> bool:
    changed = False
    deadline = time.monotonic() + max(0, timeout)
    while True:
        remaining = max(0, deadline - time.monotonic()) if timeout else 0
        try:
            ready, _, _ = select.select([fd], [], [], 0 if changed else remaining)
        except OSError as error:
            raise MouseError(f"Could not wait for receiver events: {error.strerror}",
                             code="receiver_event_wait_failed", operation="drain_events",
                             details={"errno": error.errno}) from error
        if not ready:
            return changed
        try:
            event = parse_event(os.read(fd, 128))
        except BlockingIOError:
            continue
        except OSError as error:
            raise MouseError(f"Could not read receiver event: {error.strerror}",
                             code="receiver_event_read_failed", operation="drain_events",
                             details={"errno": error.errno}) from error
        if event:
            current.update(event)
            changed = True


def query_status(fd: int, battery: dict[str, Any] | None = None) -> dict[str, Any]:
    with protocol_lock():
        dpi_report = read_receiver_feature(fd, DPI_REPORT, 56)
        dpi_info = decode_dpi_report(dpi_report)
        if dpi_info is None:
            raise MouseError("Receiver returned an invalid or undecodable DPI report",
                             code="invalid_dpi_report", operation="query_status",
                             details={"report_id": f"0x{DPI_REPORT:02x}"})
        polling_report = read_receiver_feature(fd, POLLING_REPORT, 9)
        polling = decode_polling_report(polling_report)
        if polling is None:
            raise MouseError("Receiver returned an unknown polling-rate code",
                             code="unknown_polling_rate", operation="query_status",
                             details={"report_id": f"0x{POLLING_REPORT:02x}", "code": polling_report[3]})
    status: dict[str, Any] = {
        "connected": True,
        "battery": None,
        "chargeState": None,
        "dpi": dpi_info["dpi"] if dpi_info else None,
        "stage": dpi_info["stage"] if dpi_info else None,
        "stages": dpi_info["stages"] if dpi_info else None,
        "polling": polling,
        "error": None,
    }
    if battery:
        status.update(battery)
    return status


def set_dpi(fd: int, value: int) -> dict[str, Any]:
    if not WRITES_ENABLED:
        raise MouseError("X11SE setting writes are disabled because they disconnect the receiver",
                         code="writes_disabled", operation="set_dpi")
    with protocol_lock():
        before = read_feature(fd, DPI_REPORT, 56)
        updated = update_dpi_report(before, value)
        send_feature(fd, updated)
        acknowledgement_error = None
        try:
            # This receiver sometimes applies the active DPI change but drops
            # its 0x04 command confirmation. Keep the wait short and verify
            # the actual feature report before deciding the write failed.
            wait_for_command_confirmation(fd, DPI_REPORT, timeout=0.5)
        except MouseError as error:
            acknowledgement_error = error

        info = None
        read_error = None
        for attempt in range(2):
            if attempt:
                time.sleep(0.2)
            try:
                info = decode_dpi_report(read_feature(fd, DPI_REPORT, 56))
                if info and info["dpi"] == value:
                    return {
                        "stage": info["stage"], "dpi": info["dpi"],
                        "stages": info["stages"],
                        "verified": True,
                        "acknowledged": acknowledgement_error is None,
                    }
            except MouseError as error:
                read_error = error

        if acknowledgement_error:
            detail = f"{acknowledgement_error}; DPI readback was {(info['dpi'] if info else None)!r}"
            if read_error:
                detail += f" ({read_error})"
            raise MouseError(detail, code="dpi_write_unverified", operation="set_dpi",
                             details={"requested_dpi": value,
                                      "readback_dpi": info["dpi"] if info else None,
                                      "acknowledgement_error": str(acknowledgement_error),
                                      "readback_error": str(read_error) if read_error else None}) from acknowledgement_error
        if read_error:
            raise MouseError(f"DPI change could not be verified: {read_error}",
                             code="dpi_readback_failed", operation="set_dpi",
                             details={"requested_dpi": value, "readback_error": str(read_error)}) from read_error
        actual = info["dpi"] if info else None
        raise MouseError(f"Receiver reported {actual!r} DPI after requesting {value}",
                         code="dpi_readback_mismatch", operation="set_dpi",
                         details={"requested_dpi": value, "readback_dpi": actual})


def set_polling(fd: int, rate: int) -> tuple[int, bool]:
    if not WRITES_ENABLED:
        raise MouseError("X11SE setting writes are disabled because they disconnect the receiver",
                         code="writes_disabled", operation="set_polling")
    with protocol_lock():
        # Remove delayed confirmations from earlier polling writes before the
        # next write, or an identical report ID can make an old ACK look fresh.
        drain_events(fd, {}, timeout=0)
        send_feature(fd, encode_polling_report(rate))
        confirmation_error = None
        try:
            wait_for_command_confirmation(fd, POLLING_REPORT, timeout=0.75)
        except MouseError as error:
            confirmation_error = error

        readback = None
        read_error = None
        for attempt in range(2):
            # The receiver applies its polling profile asynchronously. Give it
            # time to settle before asking for the feature report.
            time.sleep(0.25 if attempt == 0 else 0.4)
            try:
                readback = decode_polling_report(read_feature(fd, POLLING_REPORT, 9))
                if readback == rate:
                    return rate, confirmation_error is None
            except MouseError as error:
                read_error = error

        if confirmation_error:
            detail = f"{confirmation_error}; polling readback was {readback!r} Hz"
            if read_error:
                detail += f" ({read_error})"
            raise MouseError(detail, code="polling_write_unverified", operation="set_polling",
                             details={"requested_hz": rate, "readback_hz": readback,
                                      "acknowledgement_error": str(confirmation_error),
                                      "readback_error": str(read_error) if read_error else None}) from confirmation_error
        if read_error:
            raise MouseError(f"Polling rate could not be verified: {read_error}",
                             code="polling_readback_failed", operation="set_polling",
                             details={"requested_hz": rate, "readback_error": str(read_error)}) from read_error
        raise MouseError(f"Receiver reported {readback!r} Hz after requesting {rate} Hz",
                         code="polling_readback_mismatch", operation="set_polling",
                         details={"requested_hz": rate, "readback_hz": readback})


def device_error_status(error: str | BaseException, operation: str | None = None) -> dict[str, Any]:
    status: dict[str, Any] = {
        "connected": False, "battery": None, "chargeState": None, "dpi": None,
        "stage": None, "stages": None, "polling": None, "error": str(error),
    }
    if isinstance(error, MouseError):
        status.update({"errorCode": error.code, "operation": error.operation or operation,
                       "details": error.details})
    else:
        code = "invalid_argument" if isinstance(error, ValueError) else (
            "os_error" if isinstance(error, OSError) else "internal_error")
        status.update({"errorCode": code,
                       "operation": operation,
                       "details": {"exception_type": type(error).__name__}})
    cause = error.__cause__ if isinstance(error, BaseException) else None
    if cause:
        status["cause"] = f"{type(cause).__name__}: {cause}"
    return status


def json_line(value: dict[str, Any]) -> None:
    print(json.dumps(value, separators=(",", ":"), ensure_ascii=True), flush=True)


def status_text(status: dict[str, Any]) -> str:
    if not status.get("connected"):
        lines = ["X11SE unavailable: " + str(status.get("error") or "receiver not found")]
        if status.get("errorCode"):
            lines.append(f"Error code: {status['errorCode']}")
        if status.get("operation"):
            lines.append(f"Operation: {status['operation']}")
        if status.get("details"):
            lines.append("Details: " + json.dumps(status["details"], separators=(",", ":")))
        if status.get("cause"):
            lines.append("Cause: " + str(status["cause"]))
        return "\n".join(lines)
    battery = "--" if status.get("battery") is None else f"{status['battery']}% ({status.get('chargeState') or 'status unknown'})"
    dpi = "--" if status.get("dpi") is None else f"{status['dpi']} DPI (stage {status['stage']})"
    polling = "--" if status.get("polling") is None else f"{status['polling']} Hz"
    lines = [f"Battery: {battery}", f"DPI: {dpi}", f"Polling: {polling}"]
    if status.get("transport") == "bluetooth":
        lines.append("Transport: Bluetooth")
    for warning in status.get("warnings", []):
        lines.append("Warning: " + json.dumps(warning, separators=(",", ":")))
    return "\n".join(lines)
