import { PoseSkeleton } from "./camera-pose";
import { CameraOff } from "lucide-react";
import type { CameraPose } from "./types";

// Video-only COCO17 fixture. Never attach this pose to a camera event or upload it.
const lyingPose: CameraPose = {
  format: "movenet-coco17",
  keypoints: [
    [.50, .14, .98], [.48, .13, .96], [.52, .13, .96],
    [.46, .10, .94], [.54, .10, .94],
    [.44, .28, .98], [.59, .28, .98],
    [.42, .39, .95], [.65, .37, .95],
    [.46, .49, .94], [.67, .47, .94],
    [.46, .53, .98], [.58, .53, .98],
    [.44, .70, .97], [.61, .70, .97],
    [.48, .89, .96], [.64, .88, .96],
  ],
};

export function PiVideoCameraPanel({ active, fallen }: { active: boolean; fallen: boolean }) {
  const showPose = active && fallen;
  return <section className={`card camera-panel video-camera ${showPose ? "has-result" : ""}`} aria-label="Validasi kamera">
    <h3>Panel Validasi Kamera</h3>
    {showPose ? <div className="camera-result horizontal">
      <PoseSkeleton pose={lyingPose} outcome="horizontal" label="Keypoint tubuh: Berbaring" description="17 titik tubuh membentuk postur berbaring mendatar." />
      <div className="pose-details"><strong>Berbaring</strong><p>Posisi tubuh mendatar.</p><small>17 keypoint tubuh</small></div>
    </div> : <div className="camera-empty"><div className="video-camera-idle" aria-hidden="true"><CameraOff size={42} strokeWidth={1.3} /></div><div><strong>{active ? "Kamera tidak aktif" : "Kamera belum tersedia"}</strong><p>{active ? "Aktif saat kondisi jatuh terdeteksi." : "Menunggu koneksi perangkat."}</p></div></div>}
    <span className="camera-badge">Validasi Kamera: {showPose ? "Selesai" : "Nonaktif"}</span>
  </section>;
}
