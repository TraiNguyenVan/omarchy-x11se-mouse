import sys
import re
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import x11se_mouse as mouse


class ProtocolTests(unittest.TestCase):
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

    def test_panel_presets_match_verified_protocol_presets(self):
        panel = Path(__file__).resolve().parents[1].joinpath("Panel.qml").read_text(encoding="utf-8")
        common = panel.split('text: "POLLING RATE"', 1)[0]
        configured = tuple(int(value) for value in re.findall(r'\{ value: "(\d+)", label:', common))
        self.assertEqual(configured, mouse.COMMON_DPI_PRESETS)

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
