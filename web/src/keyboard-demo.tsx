import { useEffect, useReducer, useState } from "react";
import { ArrowLeft, Radio, RotateCcw, TriangleAlert } from "lucide-react";
import { CameraPanel, ConnectionIndicator, MetricGrid, StatusCard, figmaAsset } from "./dashboard";
import { formatTime } from "./status";
import { keyboardDemoKey, keyboardDemoReducer, keyboardDemoSnapshot } from "./keyboard-demo-state";
import "./keyboard-demo.css";

export function KeyboardDemo() {
  const [state, dispatch] = useReducer(keyboardDemoReducer, { fallAt: null });
  const [now, setNow] = useState(Date.now);
  const fallen = state.fallAt !== null;
  const snapshot = keyboardDemoSnapshot(state, now);

  useEffect(() => {
    function keydown(event: KeyboardEvent) {
      const type = keyboardDemoKey(event);
      if (!type) return;
      // Preserve native Space activation and editing inside focused controls.
      if (event.target instanceof Element && event.target.closest(
        "input, textarea, select, button, a, [contenteditable]:not([contenteditable=false]), [role=textbox], [role=button]",
      )) return;
      event.preventDefault();
      dispatch({ type, at: Date.now() });
    }
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  return <div className="keyboard-demo-page">
    <header className="keyboard-demo-header">
      <div className="keyboard-demo-brand"><img src={figmaAsset("55645.svg")} alt="" /><div><strong>SRASTA</strong><p>Demo deteksi jatuh</p></div></div>
      <div className="keyboard-demo-links"><ConnectionIndicator snapshot={snapshot} active /><a href="/"><ArrowLeft size={16} /> Kembali ke dashboard</a></div>
    </header>
    <main>
      <section className="keyboard-demo-controls" aria-label="Kontrol demo">
        <div className="keyboard-demo-caption"><Radio size={18} /><strong>SIMULASI MANUAL</strong><span>Berjalan di browser · tanpa perangkat</span></div>
        <h1>Idle → jatuh, cukup tekan Space.</h1>
        <p>Klik area halaman, lalu tekan <kbd>Space</kbd> untuk memicu jatuh atau <kbd>R</kbd> untuk kembali idle. Di HP, gunakan tombol di bawah.</p>
        <div className="keyboard-demo-actions">
          <button className="keyboard-demo-fall" aria-keyshortcuts="Space" onClick={() => dispatch({ type: "fall", at: Date.now() })}><TriangleAlert size={19} /> Simulasikan jatuh <kbd>Space</kbd></button>
          <button className="keyboard-demo-reset" aria-keyshortcuts="R" onClick={() => dispatch({ type: "reset", at: Date.now() })}><RotateCcw size={18} /> Kembali idle <kbd>R</kbd></button>
          <span className={`keyboard-demo-state ${fallen ? "fallen" : "idle"}`} role="status" aria-live="polite">{fallen ? "JATUH TERDETEKSI" : "IDLE"}</span>
        </div>
        <small>Status berasal dari tombol demo. Data CSI, kamera, dan alarm perangkat tidak digunakan. Peringatan demo hanya tampil di halaman ini.</small>
      </section>
      <div className="state-camera-grid">
        <StatusCard snapshot={snapshot} active name="Demo manual" room="Browser" manualDemo />
        <CameraPanel snapshot={snapshot} active />
      </div>
      <MetricGrid snapshot={snapshot} active alerts={snapshot.events} />
      <section className="card keyboard-demo-log" aria-label="Kejadian demo">
        <h2>Kejadian demo</h2>
        {fallen ? <div><TriangleAlert size={20} /><p><strong>Jatuh terdeteksi · Simulasi</strong><span>{formatTime(state.fallAt! / 1000)} · Dipicu manual. Tekan R untuk mengulang.</span></p></div> : <p>Belum ada kejadian. Program menunggu tombol Space.</p>}
      </section>
    </main>
    <footer className="keyboard-demo-footer">SRASTA · Simulasi interaksi, tanpa pengukuran sensor.</footer>
  </div>;
}
