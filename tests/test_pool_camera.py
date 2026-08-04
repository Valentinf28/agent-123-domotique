import unittest

from agent_123_domotique.pool_camera import (
    PoolReading,
    confirmed_reading,
    normalize_orp_text,
    reading_record,
)


class PoolCameraConfirmationTests(unittest.TestCase):
    def test_normalizes_micro_rx_nine_without_touching_other_digits(self):
        self.assertEqual(normalize_orp_text("3A"), "39")
        self.assertEqual(normalize_orp_text("42"), "42")
        self.assertIsNone(normalize_orp_text(None))

    def test_requires_two_matching_readings(self):
        first = reading_record(PoolReading(None, 420, True, "AL", "42", 0.72))
        second = reading_record(PoolReading(None, 420, True, "AL", "42", 0.75))
        self.assertIsNone(confirmed_reading([first]))
        result = confirmed_reading([first, second])
        self.assertIsNotNone(result)
        self.assertEqual(result.orp_mv, 420)
        self.assertTrue(result.alarm)

    def test_rejects_disagreement(self):
        history = [
            reading_record(PoolReading(7.2, 420, False, "72", "42", 0.8)),
            reading_record(PoolReading(7.3, 430, False, "73", "43", 0.8)),
        ]
        self.assertIsNone(confirmed_reading(history))


if __name__ == "__main__":
    unittest.main()
