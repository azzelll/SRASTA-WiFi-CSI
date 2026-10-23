"""Threshold, stale-stream and fail-safe physical-output contract."""
import unittest
from unittest.mock import Mock

from srasta_csi.device_panel import Hardware, Indicator, LED_PINS, buzzer_gate, select_indicator


def live(score=.4):
    return dict(source="live", simulation=False, monitoring_online=True,
                serial_connected=True, state_verified=True, stream_age_s=.02,
                updated_at_s=100., observed_at_s=100., fall_confidence=score)


class IndicatorTests(unittest.TestCase):
    def test_boundaries_seventy_five_yellow_eighty_five_red(self):
        for score, expected in [(0, "green"), (.5, "green"), (.7, "green"),
                                (.7499, "green"), (.75, "yellow"), (.8, "yellow"),
                                (.8499, "yellow"), (.85, "red"), (1, "red")]:
            with self.subTest(score=score):
                self.assertEqual(select_indicator(live(score), now=100).level, expected)

    def test_missing_invalid_or_unverified_score_never_looks_green(self):
        for score in [None, True, "0.9", float("nan"), float("inf"), -.1, 1.1]:
            with self.subTest(score=score):
                self.assertEqual(select_indicator(live(score), now=100).level, "waiting")
        self.assertEqual(select_indicator({**live(), "state_verified": False}, now=100).level, "waiting")

    def test_replay_simulation_disconnected_or_stale_stream_is_offline(self):
        for change in [{"source": "simulator"}, {"source": "replay"}, {"simulation": True},
                       {"monitoring_online": False}, {"serial_connected": False},
                       {"observed_at_s": 96}, {"updated_at_s": 96},
                       {"observed_at_s": 102}, {"stream_age_s": 4},
                       {"stream_age_s": float("nan")}, {"updated_at_s": None}]:
            with self.subTest(change=change):
                self.assertEqual(select_indicator({**live(.9), **change}, now=100).level, "offline")
        for value in [None, [], {}, "bad"]:
            self.assertEqual(select_indicator(value, now=100).level, "offline")

    def test_dead_backend_clock_and_boundary_age(self):
        self.assertEqual(select_indicator(live(.9), now=103).level, "red")
        self.assertEqual(select_indicator(live(.9), now=103.01).level, "offline")

    def test_buzzer_pattern_and_silent_states(self):
        self.assertTrue(buzzer_gate("red", .05))
        self.assertFalse(buzzer_gate("red", .15))
        self.assertTrue(buzzer_gate("red", .26))
        self.assertTrue(buzzer_gate("yellow", .1))
        self.assertFalse(buzzer_gate("yellow", .3))
        self.assertFalse(buzzer_gate("yellow", .9))
        for state in ["green", "waiting", "offline", "stopped"]:
            self.assertFalse(buzzer_gate(state, 0))


class HardwareTests(unittest.TestCase):
    def setUp(self):
        self.pins, self.duties = {}, []
        self.gpio = Mock(BCM=11, OUT=0, LOW=0, HIGH=1)
        def output(pins, value):
            for pin in pins if isinstance(pins, list) else [pins]:
                self.pins[pin] = value
            self.assertLessEqual(sum(self.pins.get(p, 0) for p in LED_PINS.values()), 1)
        self.gpio.output.side_effect = output
        self.gpio.PWM.return_value.ChangeDutyCycle.side_effect = self.duties.append
        self.device = Mock()

    def test_red_yellow_green_offline_exclusive_outputs_and_silent_disconnect(self):
        hw = Hardware(self.gpio, self.device, buzzer_mode="passive")
        try:
            for level, pin in [("red", 17), ("yellow", 27), ("green", 22)]:
                hw.update(Indicator(level, level), 0)
                self.assertEqual(self.pins[pin], 1)
            hw.update(Indicator("red", "INDIKASI JATUH"), 0)
            self.assertEqual(self.duties[-1], 50)
            hw.update(Indicator("offline", "CSI OFFLINE"), 0)
            self.assertEqual(self.duties[-1], 0)
            self.assertFalse(any(self.pins.values()))
        finally:
            hw.close()
        self.gpio.PWM.return_value.stop.assert_called_once()
        self.gpio.cleanup.assert_called_once()

    def test_buzzer_off_does_not_claim_pin_eighteen(self):
        hw = Hardware(self.gpio, self.device, buzzer_mode="off")
        hw.update(Indicator("red", "INDIKASI JATUH"), 0)
        hw.close()
        self.assertNotIn(18, hw.claimed)
        self.gpio.PWM.assert_not_called()

    def test_cleanup_releases_gpio_even_when_pwm_fails(self):
        hw = Hardware(self.gpio, self.device, buzzer_mode="passive")
        self.gpio.PWM.return_value.stop.side_effect = OSError("disconnected")
        hw.close()
        self.gpio.cleanup.assert_called_once()
        self.device.cleanup.assert_called_once()


if __name__ == "__main__":
    unittest.main()
