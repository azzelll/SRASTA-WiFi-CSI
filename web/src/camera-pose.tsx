import type { CameraPose, CameraValidation } from "./types";

const MIN_SCORE = 0.3;
const BONES = [
  [0, 1], [0, 2], [1, 3], [2, 4], [0, 5], [0, 6],
  [5, 6], [5, 7], [7, 9], [6, 8], [8, 10],
  [5, 11], [6, 12], [11, 12], [11, 13], [13, 15], [12, 14], [14, 16],
] as const;

export function poseGeometry(pose: CameraPose | null | undefined) {
  if (pose?.format !== "movenet-coco17" || !Array.isArray(pose.keypoints) || pose.keypoints.length !== 17) return null;
  if (pose.keypoints.some(point => !Array.isArray(point) || point.length !== 3 ||
    point.some(value => typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1))) return null;
  const points = pose.keypoints.flatMap(([y, x, score], index) => score >= MIN_SCORE ? [{ index, x, y }] : []);
  if (points.length < 4) return null;
  const visible = new Set(points.map(point => point.index));
  const bones = BONES.filter(([start, end]) => visible.has(start) && visible.has(end));
  const width = Math.max(...points.map(point => point.x)) - Math.min(...points.map(point => point.x));
  const height = Math.max(...points.map(point => point.y)) - Math.min(...points.map(point => point.y));
  if (bones.length < 2 || Math.hypot(width, height) < 0.03) return null;
  return { points, bones };
}

export function poseTitle(outcome: CameraValidation["outcome"]) {
  return outcome === "horizontal" ? "Berbaring" : outcome === "not_horizontal" ? "Postur tegak" :
    outcome === "error" ? "Kamera terhambat" : "Postur belum jelas";
}

export function PoseSkeleton({ pose, outcome }: { pose: CameraPose | null | undefined; outcome: CameraValidation["outcome"] }) {
  const geometry = outcome !== "error" ? poseGeometry(pose) : null;
  return (
    <div className={`pose-viewer ${geometry ? "has-pose" : "no-pose"}`}>
      {geometry ? (
        <svg viewBox="0 0 192 192" role="img" aria-label={`Skeleton dari kamera: ${poseTitle(outcome)}`}>
          <desc>Koordinat tubuh pada satu cuplikan saat kejadian. Titik dengan skor rendah tidak ditampilkan.</desc>
          <path className="pose-frame" d="M12 35V12h23M157 12h23v23M180 157v23h-23M35 180H12v-23" aria-hidden="true" />
          <g className="pose-bones">
            {geometry.bones.map(([start, end]) => {
              const a = pose!.keypoints[start], b = pose!.keypoints[end];
              return <line key={`${start}-${end}`} x1={a[1] * 192} y1={a[0] * 192} x2={b[1] * 192} y2={b[0] * 192} />;
            })}
          </g>
          <g className="pose-joints">{geometry.points.map(point => <circle key={point.index} cx={point.x * 192} cy={point.y * 192} r={2.7} />)}</g>
        </svg>
      ) : (
        <div className="pose-unavailable"><span aria-hidden="true">—</span><p>{outcome === "error" ? "Tidak ada cuplikan" : pose ? "Titik tubuh belum jelas" : "Koordinat belum tersedia"}</p></div>
      )}
    </div>
  );
}
