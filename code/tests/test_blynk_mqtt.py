from __future__ import annotations

import unittest
import time
from types import SimpleNamespace

from srasta_csi.blynk_mqtt import BlynkMQTTAdapter, values_from_status


class FakeMQTT:
    def __init__(self):
        self.published = []
        self.subscribed = []
        self.connected_to = None
        self.credentials = None

    def username_pw_set(self, user, token):
        self.credentials = (user, token)

    def connect_async(self, host, port, keepalive):
        self.connected_to = (host, port, keepalive)

    def loop_start(self):
        pass

    def disconnect(self):
        pass

    def loop_stop(self):
        pass

    def subscribe(self, topic, qos):
        self.subscribed.append((topic, qos))

    def publish(self, topic, payload, qos):
        self.published.append((topic, payload, qos))


class BlynkMQTTTests(unittest.TestCase):
    def test_simulation_events_are_labeled_and_do_not_suppress_live_events(self):
        fake = FakeMQTT()
        adapter = BlynkMQTTAdapter("test-token",on_acknowledge=lambda: None,on_assistance=lambda:None,status_provider=lambda:{"simulation_mode":True},client=fake)
        adapter._latest = {"simulation_mode":True}
        adapter._event("srasta_critical","critical",100)
        adapter._latest = {"simulation_mode":False}
        adapter._event("srasta_critical","critical",101)
        self.assertEqual(fake.published,[("event/srasta_critical","SIMULASI: critical",1),("event/srasta_critical","critical",1)])

    def test_activity_uses_frozen_motion_threshold(self):
        status = {"public_state": "normal", "simulation_mode": False,
                  "transport": {"connected": True}, "stream_age_s": 0.1,
                  "inferred_at_s": time.time(), "inference_latency_ms": 0.3,
                  "motion_energy": 0.0005, "motion_threshold": 0.0003443831}
        self.assertEqual(values_from_status(status, cloud_connected=True)[2], "Gerakan terdeteksi")

    def test_stale_stream_clears_breathing_probability_and_signal(self):
        status = {"public_state": "normal", "simulation_mode": False,
                  "transport": {"connected": True}, "stream_age_s": 12,
                  "inferred_at_s": time.time()-12, "inference_latency_ms": 0.3,
                  "fall_probability": 0.9, "breathing_estimate_bpm": 18,
                  "breathing_quality": 90, "latest_csi": {"rssi_dbm": -40}}
        values = values_from_status(status, cloud_connected=True)
        self.assertEqual(values[1], "Status terakhir: Normal; pemantauan terputus")
        self.assertEqual((values[3],values[4],values[5],values[6]), ("","0","",""))

    def test_offline_transition_publishes_health_without_waiting_for_interval(self):
        fake = FakeMQTT()
        status = {"public_state": "normal", "transport": {"connected": True}, "stream_age_s": 0}
        adapter = BlynkMQTTAdapter("test-token",on_acknowledge=lambda: None,on_assistance=lambda: None,status_provider=lambda:status,client=fake)
        adapter._on_connect(fake,None,None,0,None)
        adapter.update(status,now_s=100)
        count = len(fake.published)
        adapter.update({**status,"transport":{"connected":False}},now_s=101)
        self.assertGreater(len(fake.published),count+1)
        self.assertIn(("ds/Fall Anomaly Confidence/erase","",1),fake.published)

    def test_redirect_uses_official_tls_uri_and_duplicate_qos_is_not_applied_twice(self):
        fake = FakeMQTT()
        actions = []
        status = {"public_state": "normal"}
        adapter = BlynkMQTTAdapter("test-token", on_acknowledge=lambda: actions.append("ack"), on_assistance=lambda: None, status_provider=lambda: status, client=fake)
        adapter.start()
        adapter._on_message(fake, None, SimpleNamespace(topic="downlink/redirect", payload=b"mqtts://sgp1.blynk.cloud:8883"))
        adapter.update(status)
        self.assertEqual(fake.connected_to, ("sgp1.blynk.cloud", 8883, 45))
        adapter._on_message(fake, None, SimpleNamespace(topic="downlink/redirect", payload=b"mqtts://untrusted.example:8883"))
        adapter.update(status)
        self.assertEqual(fake.connected_to[0], "sgp1.blynk.cloud")
        self.assertEqual(adapter.last_error, "invalid Blynk redirect")
        adapter._on_message(fake, None, SimpleNamespace(topic="downlink/ds/Acknowledge Alert", payload=b"1", mid=5, dup=False))
        adapter._on_message(fake, None, SimpleNamespace(topic="downlink/ds/Acknowledge Alert", payload=b"1", mid=5, dup=True))
        self.assertEqual(actions, ["ack"])

    def test_status_has_only_derived_fields_and_discloses_simulation(self):
        status = {
            "public_state": "critical", "local_alarm_on": True, "simulation_mode": True,
            "latest_csi": {"rssi_dbm": -50, "sender_mac": "secret", "iq_bytes": [1, 2]},
            "transport": {"connected": True}, "last_event": {"state": "critical"},
            "breathing_estimate_bpm": None, "breathing_quality": 0,
        }
        values = values_from_status(status, cloud_connected=True)
        self.assertEqual(values[0], "4")
        self.assertEqual(values[9], "1")
        self.assertEqual(values[12], "1")
        self.assertEqual(values[3], "")
        self.assertNotIn("secret", str(values))
        self.assertNotIn("iq_bytes", str(values))

    def test_persistent_connection_events_rate_limit_and_two_caregiver_inputs(self):
        fake = FakeMQTT()
        actions = []
        status = {"public_state": "normal", "transport": {"connected": True},
                  "stream_age_s": 0, "simulation_mode": False, "local_alarm_on": False}
        adapter = BlynkMQTTAdapter(
            "test-token", host="sgp1.blynk.cloud", on_acknowledge=lambda: actions.append("ack"),
            on_assistance=lambda: actions.append("assistance"), status_provider=lambda: status,
            client=fake, event_interval_s=60,
        )
        adapter.start()
        self.assertEqual(fake.connected_to, ("sgp1.blynk.cloud", 8883, 45))
        adapter._on_connect(fake, None, None, 0, None)
        self.assertIn(("downlink/ds/#", 1), fake.subscribed)
        adapter.update(status, now_s=100)
        status = {**status, "public_state": "critical", "local_alarm_on": True}
        adapter.update(status, now_s=101)
        adapter.update(status, now_s=102)
        self.assertEqual(sum(topic == "event/srasta_critical" for topic, _, _ in fake.published), 1)
        self.assertIn(("ds/System State Code", "4", 1), fake.published)
        adapter._on_message(fake, None, SimpleNamespace(topic="downlink/ds/Acknowledge Alert", payload=b"1"))
        adapter._on_message(fake, None, SimpleNamespace(topic="downlink/ds/Request Assistance", payload=b"1"))
        adapter._on_message(fake, None, SimpleNamespace(topic="downlink/ds/Simulation Mode", payload=b"1"))
        self.assertEqual(actions, ["ack", "assistance"])
        self.assertIn(("ds/Acknowledge Alert", "0", 1), fake.published)
        self.assertIn(("ds/Request Assistance", "0", 1), fake.published)
        adapter.close()


if __name__ == "__main__":
    unittest.main()
