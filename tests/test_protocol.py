import sys
import io
import json
import contextlib
import unittest
import importlib.machinery
import importlib.util
import tempfile
import os
from types import SimpleNamespace
from unittest.mock import patch, mock_open
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import x11se_mouse as mouse
import hid_discovery
from model_catalog import X11SE

loader = importlib.machinery.SourceFileLoader("x11se_cli", str(Path(__file__).resolve().parents[1] / "bin/x11se-mouse"))
spec = importlib.util.spec_from_loader(loader.name, loader)
cli = importlib.util.module_from_spec(spec)
loader.exec_module(cli)


class ProtocolTests(unittest.TestCase):
    def test_cache_save_does_not_follow_preplaced_temp_symlink(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            target = root / "victim"
            target.write_text("unchanged")
            cache = root / "x11se-mouse.json"
            cache.with_suffix(".tmp").symlink_to(target)
            with patch.object(cli, "cache_path", return_value=cache):
                cli.save_cached_status({"battery": 55})
            self.assertEqual(target.read_text(), "unchanged")
            self.assertEqual(cache.read_text(), '{"battery":55}')

    def test_private_cache_round_trip_and_permissions(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            cache = Path(directory) / "omarchy" / "x11se-mouse" / "status.json"
            with patch.object(cli, "cache_path", return_value=cache):
                cli.save_cached_status({"battery": 55})
                self.assertEqual(cli.load_cached_status(), {"battery": 55})
                self.assertEqual(cache.parent.stat().st_mode & 0o777, 0o700)
                self.assertEqual(cache.stat().st_mode & 0o777, 0o600)
                self.assertEqual(cli.take_cache_warnings(), [])

    def test_unsafe_directory_and_symlink_are_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            unsafe = root / "unsafe"
            unsafe.mkdir(mode=0o777)
            unsafe.chmod(0o777)
            target = root / "target"
            target.mkdir()
            link = root / "link"
            link.symlink_to(target, target_is_directory=True)
            for base in (unsafe, link):
                with self.subTest(base=base), patch.object(cli, "cache_path", return_value=base / "private" / "status.json"):
                    cli.save_cached_status({"battery": 55})
                    self.assertEqual(cli.take_cache_warnings()[0]["code"], "cache_unavailable")
            self.assertEqual(list(target.iterdir()), [])

    def test_foreign_owned_directory_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            actual_fstat = os.fstat
            def fstat(fd):
                info = actual_fstat(fd)
                if info.st_ino == root.stat().st_ino:
                    return SimpleNamespace(st_uid=os.geteuid() + 1234, st_mode=info.st_mode)
                return info
            with patch.object(cli, "cache_path", return_value=root / "private" / "status.json"), \
                 patch.object(cli.os, "fstat", side_effect=fstat):
                cli.save_cached_status({"battery": 55})
                self.assertEqual(cli.take_cache_warnings()[0]["code"], "cache_unavailable")
            self.assertFalse((root / "private").exists())

    def test_cache_file_symlink_is_not_read_or_written(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            target = root / "victim"
            target.write_text('{"battery":99}')
            cache = root / "status.json"
            cache.symlink_to(target)
            with patch.object(cli, "cache_path", return_value=cache):
                self.assertIsNone(cli.load_cached_status()["battery"])
                cli.save_cached_status({"battery": 55})
                self.assertEqual(len(cli.take_cache_warnings()), 2)
            self.assertEqual(target.read_text(), '{"battery":99}')
            self.assertTrue(cache.is_symlink())

    def test_replacing_cache_entry_during_save_does_not_follow_symlink(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            target = root / "victim"
            target.write_text("unchanged")
            cache = root / "status.json"
            cache.write_text('{}')
            replace = os.replace
            def swap_before_replace(src, dst, **kwargs):
                cache.unlink()
                cache.symlink_to(target)
                return replace(src, dst, **kwargs)
            with patch.object(cli, "cache_path", return_value=cache), \
                 patch.object(cli.os, "replace", side_effect=swap_before_replace):
                cli.save_cached_status({"battery": 55})
            self.assertEqual(target.read_text(), "unchanged")
            self.assertFalse(cache.is_symlink())
            self.assertEqual(json.loads(cache.read_text()), {"battery": 55})

    def test_swapped_directory_does_not_redirect_write(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            private = root / "private"
            private.mkdir(mode=0o700)
            external = root / "external"
            external.mkdir()
            cache = private / "status.json"
            replace = os.replace
            def swap_before_replace(src, dst, **kwargs):
                private.rename(root / "moved")
                private.symlink_to(external, target_is_directory=True)
                return replace(src, dst, **kwargs)
            with patch.object(cli, "cache_path", return_value=cache), \
                 patch.object(cli.os, "replace", side_effect=swap_before_replace):
                cli.save_cached_status({"battery": 55})
            self.assertEqual(list(external.iterdir()), [])
            self.assertEqual(json.loads((root / "moved" / "status.json").read_text()), {"battery": 55})

    def test_status_continues_when_cache_is_unsafe(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            root.chmod(0o777)
            device_fd = os.open(os.devnull, os.O_RDONLY)
            with patch.object(cli, "cache_path", return_value=root / "private" / "status.json"), \
                 patch.object(mouse, "open_device", return_value=(device_fd, "mock")), \
                 patch.object(mouse, "protocol_lock", side_effect=contextlib.nullcontext), \
                 patch.object(mouse, "drain_events"), \
                 patch.object(mouse, "query_status", return_value={"connected": True, "dpi": 800}):
                result = cli.status_once(None)
            self.assertTrue(result["connected"])
            self.assertEqual(result["dpi"], 800)
            self.assertTrue(any(w["code"] == "cache_unavailable" for w in result["warnings"]))

    def test_presets_existing_file_round_trip(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            path = Path(directory) / "omarchy" / "x11se-presets.json"
            path.parent.mkdir()
            values = X11SE["defaultPresets"]
            path.write_text(json.dumps(values))
            with patch.object(cli, "presets_path", return_value=path):
                self.assertEqual(cli.load_presets(), values)
                changed = [450] + values[1:]
                cli.save_presets(changed)
                self.assertEqual(cli.load_presets(), changed)
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_presets_reject_symlinks_and_unsafe_directory(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            target = root / "victim"
            target.write_text("unchanged")
            path = root / "x11se-presets.json"
            path.symlink_to(target)
            with patch.object(cli, "presets_path", return_value=path):
                with self.assertRaises(OSError): cli.load_presets()
                with self.assertRaises(OSError): cli.save_presets(X11SE["defaultPresets"])
            self.assertEqual(target.read_text(), "unchanged")
            unsafe = root / "unsafe"
            unsafe.mkdir(mode=0o777)
            unsafe.chmod(0o777)
            with patch.object(cli, "presets_path", return_value=unsafe / path.name):
                with self.assertRaises(PermissionError): cli.save_presets(X11SE["defaultPresets"])
            self.assertFalse((unsafe / path.name).exists())
            link = root / "link"
            link.symlink_to(unsafe, target_is_directory=True)
            with patch.object(cli, "presets_path", return_value=link / path.name):
                with self.assertRaises(OSError): cli.save_presets(X11SE["defaultPresets"])

    def test_presets_entry_swap_does_not_write_target(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            path = root / "x11se-presets.json"
            target = root / "victim"
            path.write_text("[]")
            target.write_text("unchanged")
            replace = os.replace
            def swap(src, dst, **kwargs):
                path.unlink()
                path.symlink_to(target)
                return replace(src, dst, **kwargs)
            with patch.object(cli, "presets_path", return_value=path), patch.object(cli.os, "replace", side_effect=swap):
                cli.save_presets(X11SE["defaultPresets"])
            self.assertEqual(target.read_text(), "unchanged")
            self.assertEqual(json.loads(path.read_text()), X11SE["defaultPresets"])

    def test_presets_cli_reports_unsafe_path_and_rejects_invalid_values(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            root.chmod(0o777)
            with patch.object(cli, "presets_path", return_value=root / "presets.json"):
                for args in (["get-presets"], ["save-presets", json.dumps(X11SE["defaultPresets"])]):
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        self.assertEqual(cli.main(args), 2)
                    self.assertFalse(json.loads(output.getvalue())["ok"])
            with self.assertRaises(ValueError): cli.save_presets([800] * 7)

    def report(self):
        packet = bytearray(56)
        packet[0:3] = bytes([mouse.DPI_REPORT, 56, 1])
        packet[5] = 1
        packet[8] = 0x12
        packet[24] = 1
        packet[25] = 0xff
        packet[49] = 3
        packet[50:52] = sum(packet[3:50]).to_bytes(2, "big")
        return packet

    def test_dpi_encode_decode_and_active_stage_update(self):
        self.assertEqual(mouse.encode_dpi(800), (0x12, 0, False, False))
        self.assertEqual(mouse.encode_dpi(22000)[2:], (True, False))
        packet = self.report()
        self.assertEqual(mouse.decode_dpi_report(packet)["dpi"], 800)
        changed = mouse.update_dpi_report(packet, 1600)
        info = mouse.decode_dpi_report(changed)
        self.assertEqual(info["dpi"], 1600)
        self.assertEqual(info["stage"], 1)
        self.assertEqual(changed[25:50], packet[25:50])

    def test_polling_report_encodes_supported_rates(self):
        self.assertEqual(mouse.decode_polling_report(mouse.encode_polling_report(500)), 500)
        self.assertEqual(mouse.encode_polling_report(1000)[3:5], bytes([1, 0xFE]))
        with self.assertRaises(ValueError):
            mouse.encode_polling_report(333)

    def test_polling_write_accepts_matching_readback_when_ack_is_lost(self):
        with patch.object(mouse, "drain_events"), \
             patch.object(mouse, "send_feature"), \
             patch.object(mouse, "wait_for_command_confirmation",
                          side_effect=mouse.MouseError("Receiver did not acknowledge report 0x06")), \
             patch.object(mouse, "read_feature", return_value=mouse.encode_polling_report(500)), \
             patch.object(mouse.time, "sleep"):
            self.assertEqual(mouse.set_polling(1, 500), (500, False))

    def test_polling_write_rejects_mismatched_readback(self):
        with patch.object(mouse, "drain_events"), \
             patch.object(mouse, "send_feature"), \
             patch.object(mouse, "wait_for_command_confirmation"), \
             patch.object(mouse, "read_feature", return_value=mouse.encode_polling_report(250)), \
             patch.object(mouse.time, "sleep"):
            with self.assertRaisesRegex(mouse.MouseError, "reported 250 Hz"):
                mouse.set_polling(1, 500)

    def test_common_dpi_presets_round_trip_exactly(self):
        for dpi in mouse.COMMON_DPI_PRESETS:
            with self.subTest(dpi=dpi):
                encoded = mouse.encode_dpi(dpi)
                self.assertEqual(mouse.decode_dpi_value(*encoded), dpi)
        self.assertEqual(mouse.COMMON_DPI_PRESETS, (400, 800, 1600, 2400, 3200, 5000, 22000))

    def test_capabilities_cli_matches_protocol_and_assets(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(mouse, "open_device", side_effect=AssertionError("unexpected HID access")):
            self.assertEqual(cli.main(["capabilities"]), 0)
        model = json.loads(output.getvalue())
        self.assertEqual(model, X11SE)
        self.assertEqual(tuple(model["defaultPresets"]), mouse.COMMON_DPI_PRESETS)
        self.assertEqual(model["pollingRates"], sorted(mouse.POLLING_CODES))
        for appearance in model["appearances"]:
            self.assertTrue((Path(__file__).resolve().parents[1] / appearance["asset"]).is_file())

    def test_discovery_matches_only_registered_identity_and_interface(self):
        path = "/sys/class/hidraw/hidraw9"
        def discover(identity, interface):
            def open_file(name, *args, **kwargs):
                content = f"HID_ID={identity}\n" if name.endswith("uevent") else interface
                return mock_open(read_data=content)()
            with patch.object(hid_discovery.glob, "glob", return_value=[path]), \
                 patch.object(hid_discovery.os.path, "realpath", return_value="/sys/usb/1/device"), \
                 patch("builtins.open", side_effect=open_file):
                return hid_discovery.find_hidraw([X11SE], [])
        self.assertEqual(discover("0003:00001D57:0000FA60", "02"), (X11SE, "/dev/hidraw9"))
        self.assertIsNone(discover("0003:00001D57:0000FA61", "02"))
        self.assertIsNone(discover("0003:00001D57:0000FA60", "01"))

    def test_status_cli_json_contract(self):
        expected = {"connected": True, "battery": 55, "dpi": 800, "polling": 500, "stage": 1}
        output = io.StringIO()
        with patch.object(cli, "status_once", return_value=expected), contextlib.redirect_stdout(output):
            self.assertEqual(cli.main(["status", "--json"]), 0)
        self.assertEqual(json.loads(output.getvalue()), expected)

    def test_command_ack_matches_report_id_and_status(self):
        self.assertEqual(mouse.parse_command_confirmation(bytes([0, 0, 0x50, 0, 0x04]), 0x04), 0)
        self.assertEqual(mouse.parse_command_confirmation(bytes([0, 0, 0x50, 1, 0x06]), 0x06), 1)
        self.assertIsNone(mouse.parse_command_confirmation(bytes([0, 0, 0x50, 0, 0x06]), 0x04))

    def test_battery_event_validation(self):
        self.assertEqual(mouse.parse_event(bytes([0, 0, 0x40, 3, 59])),
                         {"battery": 59, "chargeState": "charging"})
        self.assertIsNone(mouse.parse_event(bytes([0, 0, 0x40, 3, 101])))


if __name__ == "__main__":
    unittest.main()
