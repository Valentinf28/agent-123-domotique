import unittest

from PIL import Image

from agent_123_domotique.pool_camera import (
    PoolReading,
    _quantile_image,
    _vote_characters,
    confirmed_reading,
    normalize_orp_text,
    reading_record,
)


class PoolCameraConfirmationTests(unittest.TestCase):
    def test_uses_the_40_percentile_for_a_multiplexed_burst(self):
        images = [Image.new("RGB", (1, 1), (value, value, value)) for value in (10, 20, 30, 200, 250)]
        self.assertEqual(_quantile_image(images).getpixel((0, 0)), (30, 30, 30))

    def test_votes_each_orp_digit_across_the_burst(self):
        values = ["39", "39", "29", "29", "39", "89", "38", "69", "83"]
        self.assertEqual(_vote_characters(values), "39")

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
