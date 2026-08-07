import unittest

from pool_camera import (
    _classify_temporal_profile,
    _prefer_frame_consensus,
    _prefer_orp_consensus,
    _vote_characters_with_confidence,
    confirmed_reading,
    normalize_ph_text,
)


class ConfirmedReadingTests(unittest.TestCase):
    def test_known_multiplexed_alarm_alias_is_normalized(self):
        self.assertEqual(normalize_ph_text("91"), "91")
        self.assertEqual(normalize_ph_text("0L"), "AL")
        self.assertEqual(normalize_ph_text("72"), "72")

    def test_strong_frame_vote_wins_over_conflicting_temporal_profile(self):
        text, confidence = _prefer_frame_consensus("33", 0.72, "69", 0.8)
        self.assertEqual(text, "69")
        self.assertEqual(confidence, 0.8)

    def test_weak_frame_vote_does_not_replace_temporal_profile(self):
        text, confidence = _prefer_frame_consensus("69", 0.72, "33", 0.45)
        self.assertEqual(text, "69")
        self.assertEqual(confidence, 0.72)

    def test_weak_orp_vote_replaces_known_33_multiplexing_artifact(self):
        text, confidence = _prefer_orp_consensus("33", 0.72, "69", 0.45)
        self.assertEqual(text, "69")
        self.assertGreaterEqual(confidence, 0.55)

    def test_temporal_nine_is_not_forced_to_three_when_left_top_is_lit(self):
        text, confidence = _classify_temporal_profile({
            "a": 1.0,
            "b": 0.90,
            "c": 0.86,
            "d": 0.82,
            "e": 0.20,
            "f": 0.78,
            "g": 1.0,
        })
        self.assertEqual(text, "9")
        self.assertGreaterEqual(confidence, 0.55)

    def test_temporal_three_still_uses_fast_path(self):
        text, confidence = _classify_temporal_profile({
            "a": 1.0,
            "b": 0.92,
            "c": 0.88,
            "d": 0.84,
            "e": 0.12,
            "f": 0.18,
            "g": 1.0,
        })
        self.assertEqual(text, "3")
        self.assertGreaterEqual(confidence, 0.70)

    def test_clear_frame_vote_is_accepted(self):
        text, confidence = _vote_characters_with_confidence(
            ["62", "63", "68", "68", "68", "68", "62", "68"]
        )
        self.assertEqual(text, "68")
        self.assertGreaterEqual(confidence, 0.55)

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
