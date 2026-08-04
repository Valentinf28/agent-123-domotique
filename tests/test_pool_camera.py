import unittest
from unittest.mock import patch

from PIL import Image

from agent_123_domotique.pool_camera import (
    PoolReading,
    _classify_temporal_profile,
    _quantile_image,
    _vote_characters,
    _vote_characters_with_confidence,
    _connected_digit_ranges,
    confirmed_reading,
    normalize_orp_text,
    normalize_ph_text,
    read_pool_images,
    reading_record,
)


class PoolCameraConfirmationTests(unittest.TestCase):
    def test_uses_the_40_percentile_for_a_multiplexed_burst(self):
        images = [Image.new("RGB", (1, 1), (value, value, value)) for value in (10, 20, 30, 200, 250)]
        self.assertEqual(_quantile_image(images).getpixel((0, 0)), (30, 30, 30))

    def test_votes_each_orp_digit_across_the_burst(self):
        values = ["39", "39", "29", "29", "39", "89", "38", "69", "83"]
        self.assertEqual(_vote_characters(values), "39")

    def test_trusts_a_stable_legacy_vote_across_the_burst(self):
        value, confidence = _vote_characters_with_confidence(
            ["43", "43", "43", "43", "43", "43", "43", "93"]
        )
        self.assertEqual(value, "43")
        self.assertGreaterEqual(confidence, 0.55)

    def test_separates_connected_digits_around_the_center_pixel(self):
        self.assertEqual(_connected_digit_ranges(177, 210), ((177, 193), (194, 210)))

    def test_normalizes_micro_rx_nine_without_touching_other_digits(self):
        self.assertEqual(normalize_orp_text("3A"), "39")
        self.assertEqual(normalize_orp_text("42"), "42")
        self.assertIsNone(normalize_orp_text(None))

    def test_does_not_confuse_a_real_ph_91_with_an_alarm(self):
        self.assertEqual(normalize_ph_text("91"), "91")

    def test_ph_alarm_from_multiplexed_burst_has_priority(self):
        image = Image.new("RGB", (160, 120))
        decoded = [
            (None, 0.0),
            *((None, 0.0) for _ in range(9)),
            *(("69", 0.72) for _ in range(9)),
        ]
        with (
            patch("agent_123_domotique.pool_camera._decode_two_characters", side_effect=decoded),
            patch("agent_123_domotique.pool_camera._detect_ph_alarm", return_value=(True, 0.82)),
            patch("agent_123_domotique.pool_camera._decode_temporal_characters", return_value=("69", 0.72)),
        ):
            reading = read_pool_images([image] * 9, mirror=False)
        self.assertTrue(reading.alarm)
        self.assertEqual(reading.ph_text, "AL")
        self.assertIsNone(reading.ph)

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

    def test_rejects_low_confidence_real_camera_misread(self):
        image = Image.new("RGB", (160, 120))
        decoded = [
            ("91", 0.72),
            *(("91", 0.72) for _ in range(9)),
            ("61", 0.45), ("33", 0.45), ("23", 0.45),
            ("23", 0.45), (None, 0.0), ("23", 0.45),
            ("23", 0.45), ("33", 0.45), (None, 0.0),
        ]
        with patch("agent_123_domotique.pool_camera._decode_two_characters", side_effect=decoded):
            reading = read_pool_images([image] * 9, mirror=False)
        self.assertEqual(reading.ph, 9.1)
        self.assertIsNone(reading.orp_mv)
        self.assertIsNone(reading.orp_text)

    def test_classifies_temporal_profiles_from_real_display_geometry(self):
        profiles = {
            "4": {"a": .18, "b": .65, "c": .53, "d": .19, "e": .07, "f": .30, "g": 1.0},
            "3": {"a": .79, "b": .57, "c": .41, "d": .62, "e": .10, "f": .07, "g": 1.0},
            "6": {"a": .65, "b": .17, "c": .40, "d": .53, "e": .67, "f": .69, "g": 1.0},
            "7": {"a": 1.0, "b": .10, "c": .09, "d": .20, "e": .36, "f": .51, "g": .45},
        }
        for expected, profile in profiles.items():
            with self.subTest(expected=expected):
                character, confidence = _classify_temporal_profile(profile)
                self.assertEqual(character, expected)
                self.assertGreaterEqual(confidence, 0.55)


if __name__ == "__main__":
    unittest.main()
