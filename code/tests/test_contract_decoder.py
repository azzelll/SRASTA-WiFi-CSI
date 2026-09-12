from __future__ import annotations

import json
import unittest

import numpy as np

from srasta_csi.contract import FrameValidationError, FrameValidator
from srasta_csi.decoder import FEATURE_COUNT, decode_iq_to_amplitude


def payload(sequence: int = 1, timestamp: int = 10) -> dict[str, object]:
    data = [0] * 128
    for position, magnitude in ((0, 2), (1, 3), (6, 5), (31, 7), (32, 11), (33, 13), (58, 17)):
        data[position * 2 : position * 2 + 2] = [0, magnitude]
    return {"version": 1, "sequence": sequence, "local_timestamp_us": timestamp, "sender_mac": "aa:bb:cc:dd:ee:ff", "rssi": -42, "noise_floor": -95, "channel": 1, "bandwidth": "HT20", "sig_mode": "HT", "mcs": 0, "rx_state": 0, "len": 128, "first_word_invalid": False, "iq_bytes": data}


class ContractDecoderTests(unittest.TestCase):
    def test_iq_order_fixed_mask_and_invalid_first_word(self):
        values = decode_iq_to_amplitude(payload()["iq_bytes"])
        self.assertEqual(values.shape, (FEATURE_COUNT,))
        np.testing.assert_array_equal(values[[0, 25, 26, 51]], [5, 7, 13, 17])
        self.assertNotIn(11.0, values)
        invalid = decode_iq_to_amplitude(payload()["iq_bytes"], first_word_invalid=True)
        self.assertEqual(invalid.shape, (FEATURE_COUNT,))
        np.testing.assert_array_equal(invalid[[0, 25, 26, 51]], [5, 7, 13, 17])

    def test_decoder_rejects_invalid_payload(self):
        with self.assertRaises(ValueError):
            decode_iq_to_amplitude([0] * 127)
        with self.assertRaises(ValueError):
            decode_iq_to_amplitude([0] * 127 + [128])
        with self.assertRaises(ValueError):
            decode_iq_to_amplitude(np.zeros(128, dtype=np.float32))

    def test_validator_rejects_contract_drift_and_tracks_gaps(self):
        validator = FrameValidator()
        validator.parse_json_line(json.dumps(payload()))
        validator.parse_json_line(json.dumps(payload(3, 30)))
        self.assertEqual(validator.stats()["missing_packets"], 1)
        for change in (
            {"unexpected": 1}, {"bandwidth": "HT40"}, {"channel": 6}, {"rx_state": 1},
            {"len": 127}, {"first_word_invalid": 1}, {"iq_bytes": [0] * 127 + [128]},
        ):
            with self.subTest(change=change):
                with self.assertRaises(FrameValidationError):
                    validator.validate({**payload(4, 40), **change})
        with self.assertRaises(FrameValidationError):
            validator.validate(payload(3, 40))
        with self.assertRaises(FrameValidationError):
            validator.validate(payload(4, 30))
        quarantine = validator.quarantine("bad frame", payload())
        self.assertNotIn("iq_bytes", quarantine)
        self.assertLessEqual(len(quarantine["reason"]), 240)

    def test_jsonl_fixture_and_gap_counters(self):
        validator = FrameValidator()
        frames = [
            validator.parse_json_line(json.dumps(payload(1, 10_000))),
            validator.parse_json_line(json.dumps({**payload(3, 30_000), "first_word_invalid": True})),
        ]
        self.assertEqual(len(frames), 2)
        self.assertEqual(validator.stats()["accepted_frames"], 2)
        self.assertEqual(validator.stats()["missing_packets"], 1)

    def test_parse_json_counts_quarantine_without_payload(self):
        validator = FrameValidator()
        with self.assertRaises(FrameValidationError):
            validator.parse_json_line("not-json")
        self.assertEqual(validator.stats()["quarantined_frames"], 1)
        self.assertNotIn("iq_bytes", validator.quarantine("bad"))


if __name__ == "__main__":
    unittest.main()
