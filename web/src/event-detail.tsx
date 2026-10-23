import { Check, CheckCheck, Clock3, TriangleAlert } from "lucide-react";
import type { CareEvent, CommandReceipt, Snapshot } from "./types";
import { cameraNote, eventSource, eventState, formatTime, isAlert, states } from "./status";
import { PoseSkeleton, poseTitle } from "./camera-pose";

export function EventEvidence({ event, snapshot }: { event: CareEvent; snapshot: Snapshot | null }) {
  const simulated = event.evidence.startsWith("demo") || event.evidence.startsWith("replay");
  const cameraAllowed = !simulated && !snapshot?.simulation && snapshot?.source !== "simulator" && snapshot?.source !== "replay";
  const validation = cameraAllowed ? snapshot?.camera.validations?.find(row => row.event_uid === event.event_uid) : undefined;
  const score = !simulated && Number.isFinite(event.confidence) && event.confidence >= 0 && event.confidence <= 1
    ? `${(event.confidence * 100).toFixed(0)}%` : "Tidak tersedia";
  return <div className="event-evidence">
    <dl className="event-facts">
      <div><dt>Sumber kejadian</dt><dd>{eventSource(event)}</dd></div>
      <div><dt>Skor model CSI saat kejadian</dt><dd>{score}</dd></div>
      <div><dt>Dasar peringatan</dt><dd>{event.state === "confirmed_fall" ? "Indikasi jatuh dan diam setelahnya" : event.state === "suspected_fall" ? "Indikasi anomali dari CSI" : states[eventState(event.state)].label}</dd></div>
    </dl>
    <div className="event-camera">
      <h3>Validasi kamera pada kejadian ini</h3>
      {validation ? <>
        <div className={`camera-result ${validation.outcome}`}>
          <PoseSkeleton pose={validation.pose} outcome={validation.outcome} />
          <div className="pose-details"><strong>{poseTitle(validation.outcome)}</strong><p>{validation.result}</p></div>
        </div>
        <p className="event-capture-time">Pemeriksaan kamera · {formatTime(validation.checked_at_s)}</p>
        <p className="event-evidence-note">Menunjukkan postur saat pemeriksaan, bukan kondisi saat ini. Berbaring belum memastikan tidur atau jatuh.</p>
      </> : <p className="event-evidence-note">{cameraAllowed || simulated ? cameraNote(snapshot?.camera, event) : "Validasi kamera asli tidak ditampilkan pada sesi simulasi atau replay."}</p>}
    </div>
  </div>;
}

const receiptLabels: Record<CommandReceipt["status"], string> = {
  applied: "Tersimpan di perangkat",
  pending: "Menunggu perangkat · belum diterapkan",
  expired: "Kedaluwarsa · belum diterapkan",
  rejected: "Ditolak oleh perangkat",
};

export function EventCard({ event, snapshot, receipts, busy, room, emergency, target = false, onAction, onSetupEmergency }: {
  event: CareEvent; snapshot: Snapshot | null; receipts: CommandReceipt[]; busy: boolean; room: string; emergency: string;
  target?: boolean; onAction: (event: CareEvent, action: "acknowledge" | "assistance") => void; onSetupEmergency: () => void;
}) {
  const related = receipts.filter(row => row.event_uid === event.event_uid);
  const pendingAck = related.some(row => row.action === "acknowledge" && row.status === "pending");
  const appliedAck = related.some(row => row.action === "acknowledge" && row.status === "applied");
  const assisted = related.some(row => row.action === "assistance" && row.status === "applied");
  const pendingAssistance = related.some(row => row.action === "assistance" && row.status === "pending");
  return <section className={`card alert-card ${eventState(event.state)} ${target ? "notification-target" : ""}`} aria-label="Detail kejadian">
    {target && <p className="target-label">Kejadian dari notifikasi</p>}
    <div className="section-heading"><span className={`state-chip ${eventState(event.state)}`}><TriangleAlert size={16} />{states[eventState(event.state)].label}</span><span className="source-tag">{eventSource(event)}</span></div>
    <h2>{event.state === "suspected_fall" ? "Indikasi jatuh perlu diperiksa" : event.state === "confirmed_fall" ? "Indikasi jatuh menetap setelah periode diam" : states[eventState(event.state)].description}</h2>
    <p><Clock3 size={15} />{formatTime(event.timestamp_s)} · {room}</p>
    <EventEvidence event={event} snapshot={snapshot} />
    {isAlert(event) && <div className="event-response">
      <h3>Respons caregiver</h3>
      {event.acknowledged_at_s || appliedAck ? <div className="acknowledged"><CheckCheck size={18} />Diakui caregiver{event.acknowledged_at_s ? ` · ${formatTime(event.acknowledged_at_s)}` : " · tercatat di perangkat"}</div> :
        <button className="primary" disabled={busy || pendingAck} onClick={() => onAction(event, "acknowledge")}><Check size={18} />{pendingAck ? "Menunggu konfirmasi perangkat" : "Saya sudah melihat peringatan"}</button>}
      <div className="action-grid">
        <button className="secondary" disabled={busy || assisted || pendingAssistance} onClick={() => onAction(event, "assistance")}>{assisted ? "Permintaan bantuan tercatat" : pendingAssistance ? "Permintaan menunggu perangkat" : "Minta bantuan caregiver"}</button>
        {emergency ? <a className="danger-button" href={`tel:${emergency.replace(/[^+\d]/g, "")}`}>Panggil Bantuan Darurat</a> : <button className="danger-button" onClick={onSetupEmergency}>Atur kontak darurat</button>}
      </div>
      <small>Mengakui peringatan mencatat respons Anda; status kondisi mengikuti pembaruan perangkat. Permintaan bantuan tidak melakukan panggilan otomatis.</small>
      <div className="event-receipts" role="status" aria-live="polite">{related.map(receipt => <div className="receipt" key={receipt.id}>{receipt.action === "acknowledge" ? "Pengakuan peringatan" : "Permintaan bantuan"}: <strong>{receiptLabels[receipt.status]}</strong></div>)}</div>
    </div>}
  </section>;
}
