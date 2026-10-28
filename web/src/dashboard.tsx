import { useState } from "react";
import { WifiOff } from "lucide-react";
import type { CareEvent, Snapshot, SystemState } from "./types";
import { cameraNote, eventSource, eventState, isAlert, states } from "./status";
import { PoseSkeleton, poseTitle } from "./camera-pose";
import { isPiKeyboardDemo } from "./keyboard-demo-state";
import { PiVideoCameraPanel } from "./keyboard-demo-camera";

export const figmaAsset = (file: string) => `/figma/${file}`;

// Exported Figma vectors retain their own intrinsic width and height.
export function DesignIcon({ file, className = "" }: { file: string; className?: string }) {
  return <span className={`design-icon ${className}`} aria-hidden="true"><img src={figmaAsset(file)} alt="" /></span>;
}

const visuals: Record<SystemState, { title: string; description: string; aura: string; icon: string; scene: string }> = {
  standby: { title: "MODE SIAGA", description: "Pengguna belum terdeteksi", aura: "208dd.svg", icon: "5720f.svg", scene: "32b9d.svg" },
  normal: { title: "KONDISI AMAN", description: "Aktivitas normal terdeteksi", aura: "b402c.svg", icon: "7cae4.svg", scene: "7e9a8.svg" },
  inactive: { title: "TIDAK BERGERAK", description: "Durasi inaktivitas melewati batas waspada", aura: "9b521.svg", icon: "bf319.svg", scene: "7e9a8.svg" },
  anomaly: { title: "MEMVERIFIKASI ANOMALI", description: "Indikasi anomali perlu diperiksa", aura: "1fa65.svg", icon: "1bd55.svg", scene: "ecece.svg" },
  critical: { title: "PERINGATAN DARURAT", description: "Segera periksa kondisi pengguna", aura: "7e74a.svg", icon: "d6d33.svg", scene: "a47e2.svg" },
};

export function shortTime(seconds: number | null | undefined) {
  return seconds && seconds > 1_000_000_000 ? new Date(seconds * 1000).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }) : "--:--";
}

export function duration(seconds: number | null | undefined) {
  if (seconds == null || !Number.isFinite(seconds)) return "--:--:--";
  const total = Math.max(0, Math.floor(seconds));
  return [Math.floor(total / 3600), Math.floor(total / 60) % 60, total % 60].map(n => String(n).padStart(2, "0")).join(":");
}

export function StatusCard({ snapshot, active, name, room, manualDemo = false }: { snapshot: Snapshot | null; active: boolean; name: string; room: string; manualDemo?: boolean }) {
  const piDemo = isPiKeyboardDemo(snapshot);
  manualDemo = manualDemo || piDemo;
  const state = snapshot?.state || "standby";
  const severity = active || state === "critical" || state === "anomaly" ? state : "unknown";
  const visual = visuals[severity === "unknown" ? "standby" : state];
  const latest = snapshot?.events?.filter(event => eventState(event.state) === state).sort((a, b) => b.timestamp_s - a.timestamp_s)[0];
  const confirmed = latest?.state === "confirmed_fall";
  const demoTitle = state === "critical" ? "JATUH TERDETEKSI" : "IDLE";
  return (
    <section className={`card status-card ${severity}`} aria-label={`Kondisi ${name}, ${room}`}>
      <div className="state-aura"><img src={figmaAsset(visual.aura)} alt="" /><DesignIcon file={visual.icon} className="state-symbol" /></div>
      <div className="state-copy">
        <h2 aria-label={active ? manualDemo ? demoTitle : states[state].label : undefined}>{manualDemo ? active ? demoTitle : piDemo ? "KONEKSI TERPUTUS" : "DEMO TERPUTUS" : !snapshot ? "Menunggu data" : active ? visual.title : "Status terakhir: " + states[state].label}</h2>
        <p className="state-description">{piDemo ? !active ? "Menunggu pembaruan dari perangkat" : state === "critical" ? "Segera periksa kondisi pengguna" : "Menunggu perubahan status" : manualDemo ? !active ? "Menunggu pembaruan dari Raspberry Pi" : state === "critical" ? "Simulasi jatuh dipicu manual" : "Menunggu tombol Space" : active ? confirmed ? "Indikasi jatuh terkonfirmasi" : visual.description : "Kondisi terkini belum dapat dipastikan."}</p>
        <span className="system-state">System State: {manualDemo ? state === "critical" ? "FALL DETECTED" : "IDLE" : snapshot ? state.toUpperCase() : "BELUM TERSEDIA"}</span>
        <p className="state-explanation">{piDemo ? !active ? "Kondisi terkini belum dapat dipastikan." : state === "critical" ? "Periksa kondisi pengguna dan berikan bantuan bila diperlukan." : "Status perangkat diperbarui secara otomatis." : manualDemo ? "Tekan Space untuk jatuh, R untuk kembali idle. Ini simulasi manual di browser." : state === "critical" ? "Periksa peringatan dan catat tindak lanjut. Status pengiriman dapat dilihat melalui koneksi perangkat." : state === "anomaly" ? "Hasil CSI, durasi diam, dan validasi kamera diperiksa sebelum keputusan berikutnya." : "Sistem mempertimbangkan CSI, durasi inaktivitas, napas, dan validasi kamera."}</p>
      </div>
      {state === "critical" && <DesignIcon file="bbc84.svg" className="critical-detail-icon" />}
      {!piDemo && (snapshot?.source === "simulator" || snapshot?.source === "replay" || !active) && <span className="state-source">{snapshot?.source === "simulator" ? "Simulasi" : snapshot?.source === "replay" ? "Replay" : "Belum ada data terkini"}</span>}
    </section>
  );
}

export function CameraPanel({ snapshot, active }: { snapshot: Snapshot | null; active: boolean }) {
  if (isPiKeyboardDemo(snapshot)) return <PiVideoCameraPanel active={active} fallen={snapshot?.state === "critical"} />;
  const camera = snapshot?.camera;
  const realCamera = snapshot?.source === "live" && !snapshot.simulation;
  const event = snapshot?.events?.filter(isAlert).sort((a, b) => b.timestamp_s - a.timestamp_s)[0];
  const validation = event && realCamera ? camera?.validations?.find(result => result.event_uid === event.event_uid) : undefined;
  const running = active && realCamera && camera?.active && !!event && camera.event_uid === event.event_uid;
  const result = validation && active ? validation : undefined;
  const available = active && realCamera && !!camera?.available;
  const title = running ? "Validasi Pose" : result ? "Hasil validasi postur" : available ? snapshot?.state === "inactive" ? "Kamera belum aktif / menunggu" : "Kamera tidak aktif" : "Kamera belum tersedia";
  return (
    <section className={`card camera-panel ${running ? "processing" : result ? "has-result" : ""} ${snapshot?.state === "standby" ? "standby-camera" : ""}`} aria-label="Validasi kamera" aria-busy={running}>
      <h3>Panel Validasi Kamera</h3>
      {running ? (
        <div className="camera-process">
          <div className="pose-loading" aria-hidden="true"><span /></div>
          <div className="pose-details"><strong>Membaca postur</strong><p>Kamera mengambil cuplikan untuk kejadian ini.</p><small>Skeleton muncul setelah pose terbaca.</small></div>
        </div>
      ) : result ? (
        <div className={`camera-result ${result.outcome}`}>
          <PoseSkeleton pose={result.pose} outcome={result.outcome} />
          <div className="pose-details">
            <strong>{poseTitle(result.outcome)}</strong>
            <p>{result.outcome === "horizontal" ? "Posisi mendatar. Periksa kondisi lansia secara langsung." : result.outcome === "not_horizontal" ? "Tubuh terlihat tegak, bisa berdiri atau duduk." : result.result}</p>
            <small>{result.outcome === "error" ? "Pemeriksaan" : "Cuplikan kejadian"} · {shortTime(result.checked_at_s)}</small>
            {result.outcome === "horizontal" && <span className="pose-caveat">Belum memastikan tidur atau jatuh.</span>}
          </div>
        </div>
      ) : (
        <div className="camera-empty"><DesignIcon file={snapshot?.state === "standby" ? "4b65d.svg" : "838c5.svg"} className="camera-symbol" /><div><strong>{title}</strong><p>{available ? "Aktif hanya saat kondisi anomali/kritis terdeteksi." : "Menunggu perangkat edge dan kamera yang tersedia."}</p></div></div>
      )}
      <span className={`camera-badge ${running ? "active" : ""}`}>Validasi Kamera: {running ? "Aktif" : result ? result.outcome === "uncertain" ? "Belum pasti" : result.outcome === "error" ? "Terhambat" : "Selesai" : "Nonaktif"}</span>
    </section>
  );
}

function MetricCard({ icon, title, value, note, tone, compact = false }: { icon: string; title: [string, string]; value: string | number; note: string; tone: string; compact?: boolean }) {
  return <section className={`card metric-card ${tone}`}><div className="metric-title"><DesignIcon file={icon} /><h3>{title[0]}<br />{title[1]}</h3></div><strong className={`metric-value ${compact ? "compact" : ""}`}>{value}</strong><p className="metric-note">{note}</p></section>;
}

export function MetricGrid({ snapshot, active, alerts }: { snapshot: Snapshot | null; active: boolean; alerts: CareEvent[] }) {
  const state = snapshot?.state || "standby";
  const fall = state === "critical" || state === "anomaly";
  const activity = active ? snapshot?.activity || "Belum tersedia" : "Tidak terdeteksi";
  const quality = active ? snapshot?.signal_quality : null;
  const bpm = active ? snapshot?.breathing_bpm : null;
  const open = alerts.filter(event => !event.acknowledged_at_s);
  const notificationValue = open.length ? "Perlu respons" : !active ? "--" : fall || state === "inactive" ? alerts.length ? "Diakui" : "Perlu diperiksa" : "Belum ada";
  const notificationNote = open.length ? `${open.length} peringatan belum diakui` : !active ? "Belum ada data terkini" : fall || state === "inactive" ? alerts.length ? "Peringatan telah diakui" : "Periksa kondisi terkini" : "Tidak ada peringatan aktif";
  const condition = { sleep: "Pola tidur", normal: "Pola normal", empty: "Ruangan kosong" };
  const breathingNote = active && snapshot?.breathing_condition ? condition[snapshot.breathing_condition] : bpm != null ? `Kualitas: ${snapshot?.breathing_quality ?? 0}%` : "Belum tersedia";
  return (
    <div className={`metric-grid ${isPiKeyboardDemo(snapshot) ? "video-metrics" : ""}`}>
      <MetricCard icon={fall ? "66f42.svg" : "b3250.svg"} title={["Aktivitas", "Saat Ini"]} value={activity} compact={activity.length > 12} tone={fall ? "red" : active && state !== "standby" ? state === "inactive" ? "yellow" : "green" : "slate"} note={active && snapshot?.fall_confidence != null ? `Skor jatuh: ${(snapshot.fall_confidence * 100).toFixed(0)}%` : "Skor jatuh: --"} />
      {!isPiKeyboardDemo(snapshot) && <MetricCard icon="f10af.svg" title={["Laju", "Pernapasan"]} value={bpm ?? "--"} tone="purple" note={bpm != null ? `${breathingNote} · napas/menit` : breathingNote} />}
      <MetricCard icon="a6422.svg" title={["Durasi", "Inaktivitas"]} value={duration(active ? snapshot?.stationary_duration_s : null)} tone="orange" note="Durasi diam teramati" />
      <MetricCard icon="01cd2.svg" title={["Kualitas", "Sinyal"]} value={quality == null ? "--" : quality >= 70 ? "Baik" : quality >= 40 ? "Cukup" : "Lemah"} tone="green" note={quality == null ? "Belum tersedia" : `Kualitas: ${quality.toFixed(0)}%`} />
      <MetricCard icon="e8479.svg" title={["Edge", "Processor"]} value={active ? snapshot?.source === "simulator" && !isPiKeyboardDemo(snapshot) ? "Simulasi" : "Online" : "Offline"} tone="teal" note="Raspberry Pi 4B" />
      <MetricCard icon={state === "critical" ? "631b6.svg" : "f8f09.svg"} title={["Status", "Notifikasi"]} value={notificationValue} compact={notificationValue.length > 12} tone={state === "critical" ? "red" : "yellow"} note={notificationNote} />
    </div>
  );
}

function eventTitle(event: CareEvent) {
  if (event.state === "confirmed_fall") return "Indikasi Jatuh";
  if (event.state === "suspected_fall") return "Anomali Terdeteksi";
  return { standby: "Mode Siaga", normal: "Aktivitas Normal", inactive: "Inaktivitas Terdeteksi", anomaly: "Anomali Terdeteksi", critical: "Peringatan Darurat" }[eventState(event.state)];
}

export function AlertHistory({ snapshot, active, onOpen }: { snapshot: Snapshot | null; active: boolean; onOpen: () => void }) {
  const alerts = snapshot?.events?.filter(isAlert).sort((a, b) => Number(!b.acknowledged_at_s) - Number(!a.acknowledged_at_s) || b.timestamp_s - a.timestamp_s) || [];
  const hasOpen = alerts.some(event => !event.acknowledged_at_s);
  const concerning = snapshot?.state === "critical" || snapshot?.state === "anomaly" || snapshot?.state === "inactive";
  return <section className="card alert-history">
    <div className="section-heading"><h3>Riwayat Peringatan</h3><button className="text-button" onClick={onOpen}>Lihat Semua</button></div>
    <div className="alert-history-rows">
      {!hasOpen && <div className="alert-history-row empty-history"><DesignIcon file="19cb5.svg" /><time>--:--</time><div><strong>{concerning ? "Kondisi terakhir perlu diperiksa." : "Tidak ada peringatan aktif saat ini."}</strong><p>{!active ? "Kondisi terkini belum dapat dipastikan" : concerning ? "Periksa kondisi dan tindak lanjut" : snapshot?.state === "normal" ? "Sistem berjalan normal" : "Sistem dalam mode siaga"}</p></div><span className={`history-tag ${active && !concerning ? "resolved" : "waiting"}`}>{active && !concerning ? snapshot?.state === "normal" ? "Aman" : "Siaga" : "Periksa"}</span></div>}
      {alerts.slice(0, hasOpen ? 3 : 2).map(event => {
        const state = eventState(event.state);
        const open = !event.acknowledged_at_s;
        return <button className={`alert-history-row ${state} ${open ? "unacknowledged" : ""}`} key={event.event_uid} onClick={onOpen}>
          <DesignIcon file={state === "critical" ? open ? "edec1.svg" : "10744.svg" : state === "anomaly" ? "f1a37.svg" : "8507f.svg"} />
          <time>{shortTime(event.timestamp_s)}</time><div><strong>{eventTitle(event)}</strong><p>{eventSource(event)} · {event.state === "confirmed_fall" ? "Diam setelah indikasi jatuh" : open ? "Perlu pemeriksaan caregiver" : "Respons caregiver tercatat"}</p></div><span className={`history-tag ${open ? "waiting" : "resolved"}`}>{open ? "Aktif" : "Diakui"}</span>
        </button>;
      })}
    </div>
    <p className={"history-note " + (snapshot?.state === "critical" ? "with-info" : "")}>{snapshot?.state === "critical" && <DesignIcon file="a831c.svg" />}Peringatan aktif ditampilkan paling atas. Riwayat disimpan untuk evaluasi false positive.</p>
  </section>;
}

export function MotionChart({ values, state = "normal" }: { values: number[]; state?: SystemState }) {
  const max = Math.max(...values, 0), scale = max > 0 ? max : 1;
  const points = values.map((value, i) => `${(i / (values.length - 1)) * 600},${110 - (value / scale) * 90}`).join(" ");
  return <div className={`motion-figure ${state}`}>
    <div className="chart-grid" />
    {values.length < 2 ? <div className="empty-chart"><span>Grafik muncul saat data CSI langsung mengalir.</span></div> : <>
      <svg className="motion-chart" viewBox="0 0 600 130" preserveAspectRatio="none" role="img" aria-label="Tren energi gerakan dari CSI"><polyline points={points} fill="none" stroke="currentColor" strokeWidth="2.5" vectorEffect="non-scaling-stroke" /><circle cx="600" cy={110 - (values[values.length - 1] / scale) * 90} r="4" fill="currentColor" /></svg>
      <div className="motion-scale"><span>Skala otomatis</span><span>0 – {max === 0 ? "0" : max.toExponential(1)}</span></div>
    </>}
  </div>;
}

function ActivityChart({ snapshot, motion, now, onHistory }: { snapshot: Snapshot | null; motion: { time: number; value: number }[]; now: number; onHistory: () => void }) {
  const [range, setRange] = useState(3600);
  const samples = motion.filter(row => row.time >= now / 1000 - range);
  const today = new Date(now).toDateString();
  const events = snapshot?.events?.filter(event => new Date(event.timestamp_s * 1000).toDateString() === today).sort((a, b) => a.timestamp_s - b.timestamp_s).slice(-5) || [];
  return <section className="card activity-chart">
    <div className="chart-heading"><div><h3>{isPiKeyboardDemo(snapshot) ? "Grafik Sinyal CSI" : "Grafik Aktivitas"}</h3><p>Berdasarkan intensitas sinyal CSI</p></div><div className="range-selector"><select aria-label="Rentang waktu grafik" value={range} onChange={event => setRange(Number(event.target.value))}><option value={60}>1 Menit</option><option value={300}>5 Menit</option><option value={3600}>1 Jam</option></select><DesignIcon file="7d576.svg" /></div></div>
    <MotionChart values={samples.map(row => row.value)} state={snapshot?.state} />
    {samples.length > 1 && <div className="chart-tooltip"><time>{shortTime(samples[samples.length - 1].time)}</time><span><b>Aktivitas: </b>{snapshot?.activity || "Belum tersedia"}</span></div>}
    <div className="activity-summary"><h4>Ringkasan Aktivitas Hari Ini</h4><div className="activity-chips">{events.length ? events.map(event => { const state = eventState(event.state); return <button className={`activity-chip ${state}`} key={event.event_uid} onClick={onHistory}><DesignIcon file={state === "inactive" ? "d62dc.svg" : state === "critical" || state === "anomaly" ? "edec1.svg" : "b594a.svg"} /><div><time>{shortTime(event.timestamp_s)}</time><span>{states[state].label}</span></div></button>; }) : <p className="activity-empty">Belum ada aktivitas tercatat hari ini.</p>}</div></div>
  </section>;
}

export function DashboardHome({ snapshot, active, name, room, now, motion, onAlerts, onHistory }: { snapshot: Snapshot | null; active: boolean; name: string; room: string; now: number; motion: { time: number; value: number }[]; onAlerts: () => void; onHistory: () => void }) {
  const state = snapshot?.state || "standby";
  const alerts = snapshot?.events?.filter(isAlert) || [];
  const scene = active ? visuals[state].scene : visuals.standby.scene;
  return <div className="dashboard-home">
    <div className="person-and-room">
      <div className="person-profile"><img className="profile-illustration" src={figmaAsset("23fa9.svg")} alt="" /><div><h2>{name}</h2><p><DesignIcon file="c59a2.svg" />{room}</p></div></div>
      <div className={"room-scene " + (active && state === "critical" ? "critical-scene" : "")} aria-label="Ilustrasi area pemantauan antara transmitter dan receiver"><img src={figmaAsset(scene)} alt="Ilustrasi area pemantauan" /><span className="transmitter-label">Transmitter<br />ESP32-S3</span><span className="receiver-label">Receiver<br />ESP32-S3</span></div>
    </div>
    <div className="state-camera-grid"><StatusCard snapshot={snapshot} active={active} name={name} room={room} /><CameraPanel snapshot={snapshot} active={active} /></div>
    <MetricGrid snapshot={snapshot} active={active} alerts={alerts} />
    <div className="chart-history-grid"><ActivityChart snapshot={snapshot} motion={motion} now={now} onHistory={onHistory} /><AlertHistory snapshot={snapshot} active={active} onOpen={onAlerts} /></div>
  </div>;
}

export function ConnectionIndicator({ snapshot, active }: { snapshot: Snapshot | null; active: boolean }) {
  return <span className={`connection-pill ${active ? "online" : "offline"}`}>
    {active ? <DesignIcon file={snapshot?.state === "critical" ? "39f6d.svg" : "ae9b7.svg"} /> : <WifiOff size={14} />}
    {snapshot?.source === "simulator" && !isPiKeyboardDemo(snapshot) ? "Simulasi" : snapshot?.source === "replay" ? "Replay rekaman" : active ? snapshot?.state === "standby" ? "Perangkat Siaga" : "Perangkat Online" : "Perangkat Offline"}
  </span>;
}
