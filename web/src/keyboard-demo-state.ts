import type { Snapshot } from "./types";

export interface KeyboardDemoState {
  fallAt: number | null;
}

export interface KeyboardDemoAction {
  type: "fall" | "reset";
  at: number;
}

export function keyboardDemoRequested(search: string): boolean {
  return new URLSearchParams(search).get("demo") === "keyboard";
}

export function isPiKeyboardDemo(snapshot: Snapshot | null): boolean {
  return snapshot?.simulation === true && snapshot.model.label === "SRASTA keyboard demo (Pi)"
    && (snapshot.source === "simulator" || snapshot.source === "unavailable");
}

export function keyboardDemoKey(event: Pick<KeyboardEvent,
  "key" | "repeat" | "defaultPrevented" | "isComposing" | "altKey" | "ctrlKey" | "metaKey"
>): KeyboardDemoAction["type"] | null {
  if (event.repeat || event.defaultPrevented || event.isComposing || event.altKey || event.ctrlKey || event.metaKey)
    return null;
  if (event.key === " ") return "fall";
  if (event.key.toLowerCase() === "r") return "reset";
  return null;
}

export function keyboardDemoReducer(state: KeyboardDemoState, action: KeyboardDemoAction): KeyboardDemoState {
  if (action.type === "reset") return { fallAt: null };
  return state.fallAt === null ? { fallAt: action.at } : state;
}

export function keyboardDemoSnapshot(state: KeyboardDemoState, now: number): Snapshot {
  const fallen = state.fallAt !== null;
  return {
    schema_version: 1,
    updated_at_s: now / 1000,
    observed_at_s: null,
    source: "simulator",
    simulation: true,
    state: fallen ? "critical" : "normal",
    state_verified: true,
    monitoring_online: false,
    stream_age_s: null,
    activity: fallen ? "Jatuh terdeteksi" : "Idle",
    presence: "unknown",
    motion_energy: null,
    fall_confidence: null,
    breathing_bpm: null,
    breathing_quality: 0,
    breathing_reason: "Tidak diukur pada demo manual.",
    signal_quality: null,
    capture_rate_hz: 0,
    accepted_frames: 0,
    quarantined_frames: 0,
    packet_loss_rate: null,
    inference_ms: null,
    serial_connected: false,
    serial_reconnects: 0,
    alarm: { requested: false, available: false, active: false, mode: "disabled" },
    camera: { available: false, active: false, result: "Tidak digunakan pada demo manual." },
    blynk_connected: false,
    remote: { enabled: false, connected: false },
    model: {
      label: "Demo keyboard",
      validation: "Status diubah manual, tanpa inferensi model.",
      presence_available: false,
      activity_classes_available: false,
    },
    events: state.fallAt === null ? [] : [{
      id: 1,
      event_uid: `demo-keyboard-${state.fallAt}`,
      timestamp_s: state.fallAt / 1000,
      state: "critical",
      // Required event-contract fields; simulated scores are never displayed.
      confidence: 0,
      motion_energy: 0,
      evidence: "demo_keyboard_manual",
      acknowledged_at_s: null,
      ack_source: null,
    }],
  };
}
