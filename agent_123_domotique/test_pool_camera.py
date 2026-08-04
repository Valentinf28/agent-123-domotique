import unittest

from pool_camera import confirmed_reading


class ConfirmedReadingTests(unittest.TestCase):
    def test_alarm_is_confirmed_even_when_orp_changes(self):
        reading = confirmed_reading([
            {"ph": None, "orp_mv": 680, "alarm": True, "ph_text": "AL", "orp_text": "68", "confidence": 0.7},
            {"ph": None, "orp_mv": 690, "alarm": True, "ph_text": "AL", "orp_text": "69", "confidence": 0.8},
            {"ph": None, "orp_mv": 670, "alarm": True, "ph_text": "AL", "orp_text": "67", "confidence": 0.7},
        ])
        self.assertIsNotNone(reading)
        self.assertTrue(reading.alarm)
        self.assertEqual(reading.ph_text, "AL")

    def test_orp_is_confirmed_independently_from_ph(self):
        reading = confirmed_reading([
            {"ph": 7.2, "orp_mv": 690, "alarm": False, "ph_text": "72", "orp_text": "69", "confidence": 0.7},
            {"ph": 7.3, "orp_mv": 690, "alarm": False, "ph_text": "73", "orp_text": "69", "confidence": 0.8},
            {"ph": 7.4, "orp_mv": 680, "alarm": False, "ph_text": "74", "orp_text": "68", "confidence": 0.7},
        ])
        self.assertIsNotNone(reading)
        self.assertEqual(reading.orp_mv, 690)
        self.assertEqual(reading.orp_text, "69")


if __name__ == "__main__":
    unittest.main()
