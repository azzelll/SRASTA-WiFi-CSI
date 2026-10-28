import type { Snapshot } from "./types";
import { isPiKeyboardDemo } from "./keyboard-demo-state";

// Synthetic values for the owner's video recording. Use only for rendering;
// the received snapshot, cloud data, events and freshness checks stay untouched.
export function piVideoPresentation(snapshot: Snapshot | null, active: boolean, now: number) {
  if (!active || !isPiKeyboardDemo(snapshot) || !snapshot) return null;
  const second = Math.floor(now / 1000);
  const critical = snapshot.state === "critical";
  const breathing = 18 + Math.round(Math.sin(second / 12));
  const signal = 95 + Math.round(2 * Math.sin(second / 17));
  const motion = Array.from({ length: 241 }, (_, index) => {
    const time = second - 60 + index / 4;
    const baseline = 0.0018 + 0.00035 * Math.sin(time * 2.1)
      + 0.00022 * Math.sin(time * 5.7) + 0.0004 * Math.sin(time / 3);
    const fallPeak = critical ? 0.012 * Math.exp(-(((index - 215) / 7) ** 2)) : 0;
    return { time, value: baseline + fallPeak };
  });
  const displaySnapshot: Snapshot = {
    ...snapshot,
    fall_confidence: critical ? 0.97 : 0.03,
    breathing_bpm: breathing,
    breathing_quality: 94,
    breathing_condition: "normal",
    stationary_duration_s: (critical ? 40 : 10) + second % 30,
    signal_quality: signal,
    capture_rate_hz: 100,
    accepted_frames: 248_000 + second % 10_000 * 100,
    packet_loss_rate: 0.002,
    inference_ms: 2.9 + Math.round(Math.sin(second / 8) * 2) / 10,
  };
  return { snapshot: displaySnapshot, motion };
}
