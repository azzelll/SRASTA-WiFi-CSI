import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { PoseSkeleton, poseGeometry } from "./camera-pose";
import type { CameraPose } from "./types";

function upright(): CameraPose {
  return { format: "movenet-coco17", keypoints: [
    [.16,.5,.95],[.15,.47,.9],[.15,.53,.9],[.16,.44,.9],[.16,.56,.9],
    [.3,.4,.95],[.3,.6,.95],[.45,.34,.9],[.45,.66,.9],[.57,.3,.9],[.57,.7,.9],
    [.55,.44,.95],[.55,.56,.95],[.73,.44,.9],[.73,.57,.9],[.9,.42,.9],[.9,.59,.9],
  ] };
}

describe("camera skeleton from actual payload coordinates", () => {
  it("keeps upright and horizontal coordinates in their captured orientation", () => {
    const standing = upright();
    const lying: CameraPose = { ...standing, keypoints: standing.keypoints.map(([y,x,score]) => [x,1-y,score]) };
    const a = poseGeometry(standing)!, b = poseGeometry(lying)!;
    expect(a.points[0]).toEqual({index:0,x:.5,y:.16});
    expect(b.points[0]).toEqual({index:0,x:.84,y:.5});
    expect(a.bones.length).toBeGreaterThan(10);
    const html = renderToStaticMarkup(<PoseSkeleton pose={lying} outcome="horizontal" />);
    expect(html).toContain('cx="161.28"');
    expect(html).toContain("Skeleton dari kamera: Berbaring");
    expect(html).not.toContain("<img");
  });

  it("omits uncertain joints and every connected bone", () => {
    const pose = upright();
    pose.keypoints[9][2] = .1;
    const geometry = poseGeometry(pose)!;
    expect(geometry.points.some(point => point.index === 9)).toBe(false);
    expect(geometry.bones.some(bone => bone.some(index => index === 9))).toBe(false);
  });

  it("rejects malformed, nonfinite, out-of-range, low confidence and collapsed poses", () => {
    for (const value of [NaN, Infinity, -.1, 1.1, "0.5", true]) {
      const pose = upright();
      pose.keypoints[0][0] = value as number;
      expect(poseGeometry(pose)).toBeNull();
    }
    const pose = upright();
    expect(poseGeometry({...pose,keypoints:pose.keypoints.slice(1)})).toBeNull();
    expect(poseGeometry({...pose,keypoints:pose.keypoints.map(([y,x])=>[y,x,.1])})).toBeNull();
    expect(poseGeometry({...pose,keypoints:pose.keypoints.map(()=>[.5,.5,.9])})).toBeNull();
  });

  it("never invents a skeleton for a legacy summary or failed capture", () => {
    for (const pose of [null, upright()]) {
      const html = renderToStaticMarkup(<PoseSkeleton pose={pose} outcome="error" />);
      expect(html).not.toContain("<svg");
      expect(html).toContain("Tidak ada cuplikan");
    }
    const html = renderToStaticMarkup(<PoseSkeleton pose={null} outcome="uncertain" />);
    expect(html).toContain("Koordinat belum tersedia");
  });
});
