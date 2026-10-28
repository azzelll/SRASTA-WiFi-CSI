import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { CameraPanel, ConnectionIndicator, DashboardHome, MetricGrid, StatusCard } from "./dashboard";
import { KeyboardDemo } from "./keyboard-demo";
import { isPiKeyboardDemo, keyboardDemoKey, keyboardDemoReducer, keyboardDemoRequested, keyboardDemoSnapshot } from "./keyboard-demo-state";
import { receiverStatus } from "./status";
import { piVideoPresentation } from "./keyboard-demo-presentation";

describe("manual Pi/browser demo", () => {
  it("keeps the fall latched until reset and does not manufacture sensor readings", () => {
    const idle = { fallAt: null };
    const fallen = keyboardDemoReducer(idle, { type: "fall", at: 1_800_000_000_000 });
    expect(keyboardDemoReducer(fallen, { type: "fall", at: 1_800_000_001_000 })).toBe(fallen);
    const snapshot = keyboardDemoSnapshot(fallen, 1_800_000_002_000);
    expect(snapshot.state).toBe("critical");
    expect(snapshot.simulation).toBe(true);
    expect(snapshot.fall_confidence).toBeNull();
    expect(snapshot.serial_connected).toBe(false);
    expect(snapshot.breathing_bpm).toBeNull();
    expect(keyboardDemoSnapshot(keyboardDemoReducer(fallen, { type: "reset", at: 1 }), 2).events).toEqual([]);
  });
  it("keeps Pi presentation clean while preserving provenance and connection freshness", () => {
    const snapshot = keyboardDemoSnapshot({ fallAt: null }, Date.now());
    snapshot.model.label = "SRASTA keyboard demo (Pi)";
    expect(isPiKeyboardDemo(snapshot)).toBe(true);
    expect(isPiKeyboardDemo({ ...snapshot, simulation: false })).toBe(false);
    expect(isPiKeyboardDemo({ ...snapshot, source: "live" })).toBe(false);
    expect(receiverStatus(snapshot, true)).toEqual({ ok: false, value: "Belum tersedia" });
    expect(renderToStaticMarkup(<StatusCard snapshot={snapshot} active name="Pi" room="Kamar" />)).toContain(">IDLE</h2>");
    snapshot.state = "critical";
    const html = renderToStaticMarkup(<><StatusCard snapshot={snapshot} active name="Pi" room="Kamar" /><ConnectionIndicator snapshot={snapshot} active /><MetricGrid snapshot={snapshot} active alerts={[]} /></>);
    expect(html).toContain("JATUH TERDETEKSI");
    expect(html).toContain("Perangkat Online");
    expect(html).not.toMatch(/demo|simulasi|manual|Space|simulator/i);
    expect(html).not.toContain("Indikasi jatuh terkonfirmasi");
    const stale = renderToStaticMarkup(<><StatusCard snapshot={snapshot} active={false} name="Pi" room="Kamar" /><ConnectionIndicator snapshot={snapshot} active={false} /></>);
    expect(stale).toContain("KONEKSI TERPUTUS");
    expect(stale).toContain("Perangkat Offline");
    expect(stale).not.toContain(">JATUH TERDETEKSI</h2>");
  });
  it("does not hijack held keys, shortcuts, composition, or handled events", () => {
    const event = { key: " ", repeat: false, defaultPrevented: false, isComposing: false, altKey: false, ctrlKey: false, metaKey: false };
    expect(keyboardDemoKey(event)).toBe("fall");
    expect(keyboardDemoKey({ ...event, key: "R" })).toBe("reset");
    for (const change of [{ repeat: true }, { defaultPrevented: true }, { isComposing: true }, { altKey: true }, { ctrlKey: true }, { metaKey: true }, { key: "x" }])
      expect(keyboardDemoKey({ ...event, ...change })).toBeNull();
  });
  it("renders video metrics and an evolving CSI trace only for a fresh marked Pi without changing input data", () => {
    const now = 1_800_000_002_000;
    const snapshot = keyboardDemoSnapshot({ fallAt: null }, now);
    snapshot.model.label = "SRASTA keyboard demo (Pi)";
    const original = structuredClone(snapshot);
    const idle = piVideoPresentation(snapshot, true, now)!;
    expect(snapshot).toEqual(original);
    expect(idle.snapshot.simulation).toBe(true);
    expect(idle.snapshot.source).toBe("simulator");
    expect(idle.snapshot.events).toEqual([]);
    expect(idle.snapshot.camera).toEqual(snapshot.camera);
    expect(piVideoPresentation(snapshot, false, now)).toBeNull();
    expect(piVideoPresentation({ ...snapshot, model: { ...snapshot.model, label: "Live model" } }, true, now)).toBeNull();
    expect(piVideoPresentation(null, false, now)).toBeNull();
    const fall = piVideoPresentation({ ...snapshot, state: "critical" }, true, now)!;
    expect(Math.max(...fall.motion.map(point => point.value))).toBeGreaterThan(Math.max(...idle.motion.map(point => point.value)) * 3);
    expect(piVideoPresentation(snapshot, true, now + 1000)!.motion).not.toEqual(idle.motion);
    const html = renderToStaticMarkup(<DashboardHome snapshot={idle.snapshot} motion={idle.motion} now={now} active name="Pi" room="Kamar" onAlerts={() => {}} onHistory={() => {}} />);
    expect(html).toContain("Grafik Sinyal CSI");
    expect(html).toContain("<polyline");
    expect(html).toContain("Skor jatuh: 3%");
    expect(html).not.toContain("napas/menit");
    expect(html).not.toContain("Pernapasan");
    expect(html).not.toMatch(/NaN|Infinity|simulasi|Space|pengujian/i);
  });
  it("shows the lying keypoints for the Pi video only while fallen and fresh, then clears them on reset", () => {
    const now = 1_800_000_002_000;
    const idle = keyboardDemoSnapshot({ fallAt: null }, now);
    idle.model.label = "SRASTA keyboard demo (Pi)";
    const fallen = { ...idle, state: "critical" as const };
    const html = renderToStaticMarkup(<CameraPanel snapshot={fallen} active />);
    expect(html).toContain("Keypoint tubuh: Berbaring");
    expect(html).toContain("Validasi Kamera: Selesai");
    expect(html.match(/<circle /g)).toHaveLength(17);
    const points = [...html.matchAll(/<circle[^>]* cx="([^"]+)" cy="([^"]+)"/g)];
    const width = Math.max(...points.map(point => Number(point[1]))) - Math.min(...points.map(point => Number(point[1])));
    const height = Math.max(...points.map(point => Number(point[2]))) - Math.min(...points.map(point => Number(point[2])));
    expect(width).toBeGreaterThan(height * 2);
    expect(html).not.toMatch(/demo|simulasi|manual|Space|kamera asli|cuplikan/i);
    for (const [snapshot, active] of [[idle, true], [fallen, false], [{ ...fallen, model: { ...idle.model, label: "Other simulator" } }, true]] as const) {
      expect(renderToStaticMarkup(<CameraPanel snapshot={snapshot} active={active} />)).not.toContain("Keypoint tubuh: Berbaring");
    }
    expect(fallen.camera.validations).toBeUndefined();
    expect(fallen.events).toEqual([]);
  });
  it("requires the exact browser demo route and starts idle on a new page", () => {
    expect(keyboardDemoRequested("?demo=keyboard")).toBe(true);
    expect(keyboardDemoRequested("?demo=anything")).toBe(false);
    expect(keyboardDemoRequested("")).toBe(false);
    const html = renderToStaticMarkup(<KeyboardDemo />);
    expect(html).toContain(">IDLE</h2>");
    expect(html).toContain("SIMULASI MANUAL");
    expect(html).not.toContain(">JATUH TERDETEKSI</h2>");
  });
});
