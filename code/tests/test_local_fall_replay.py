import unittest

from srasta_csi.local_fall import replay_metrics


class LocalReplayTests(unittest.TestCase):
    def test_episode_upgrade_counts_once_and_outages_are_not_zero_alert_success(self):
        events = [{"event_type": "no_person", "onset_monotonic_us": 0,
                   "event_end_monotonic_us": 10_000_000}]
        rows = [{"timestamp_monotonic_us": n*1_000_000,
                 "state": "normal" if n < 2 else "suspected_fall" if n < 5 else "confirmed_fall",
                 "alert_id": None if n < 2 else "A", "alert_start": n == 2}
                for n in range(11)]
        result = replay_metrics(events, rows, [(0, 10_000_000)])
        self.assertEqual(result["false_alert_episodes"], 1)
        self.assertEqual(result["eligible_nonfall_s"], 10.)
        outage = replay_metrics(events, [], [(0, 10_000_000)])
        self.assertIsNone(outage["false_alerts_per_hour"])
        self.assertEqual(outage["eligible_nonfall_s"], 0.)

    def test_short_postfall_truth_is_excluded_without_extending_it(self):
        event = {"event_type": "fall", "onset_monotonic_us": 1_000_000,
                 "post_event_inactivity_start_monotonic_us": 3_000_000,
                 "post_event_inactivity_end_monotonic_us": 5_000_000}
        rows = [{"timestamp_monotonic_us": n*1_000_000, "state": "normal",
                 "alert_id": None, "alert_start": False} for n in range(12)]
        result = replay_metrics([event], rows, [(0, 11_000_000)])
        self.assertEqual(result["eligible_falls"], 0)
        self.assertEqual(result["confirmation_eligible_falls"], 0)
        self.assertIsNone(result["event_recall"])


if __name__ == "__main__":
    unittest.main()
