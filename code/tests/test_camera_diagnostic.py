"""A diagnostic report must retain measured geometry and omit weak body parts."""
import copy
import unittest

from srasta_csi.camera_diagnostic import render_report, report_data


def fixture():
    # Explicitly synthetic coordinates; these are renderer tests, not captures.
    points = [[.16, .5, .95], [.15, .47, .9], [.15, .53, .9], [.16, .44, .9], [.16, .56, .9],
              [.3, .4, .95], [.3, .6, .95], [.45, .34, .9], [.45, .66, .9], [.57, .3, .9], [.57, .7, .9],
              [.55, .44, .95], [.55, .56, .95], [.73, .44, .9], [.73, .57, .9], [.9, .42, .9], [.9, .59, .9]]
    return {"software_passed": True, "frames_per_burst": 3, "images_saved": False,
            "cloud_events_sent": False, "edge_service_restored": True,
            "validation": {"outcome": "not_horizontal", "result": "Postur tegak", "checked_at_s": 100.,
                           "pose": {"format": "movenet-coco17", "keypoints": points}}}


class CameraDiagnosticTests(unittest.TestCase):
    def test_keeps_actual_coordinates_and_hides_weak_joint_with_connected_bone(self):
        value = fixture()
        value["validation"]["pose"]["keypoints"][9][2] = .1
        rendered = render_report(value)
        self.assertIn('data-joint="0" cx="96.00" cy="30.72"', rendered)
        self.assertNotIn('data-joint="9"', rendered)
        self.assertNotIn('data-bone="7-9"', rendered)
        self.assertNotIn('<img', rendered)
        self.assertNotIn('<script', rendered)
        self.assertIn('16 / 17', rendered)

    def test_no_invented_skeleton_for_missing_weak_collapsed_or_failed_pose(self):
        for kind in ("missing", "weak", "collapsed", "error"):
            value = fixture()
            if kind == "missing":
                value["validation"]["pose"] = None
            elif kind == "error":
                value["validation"]["outcome"] = "error"
            else:
                value["validation"]["pose"]["keypoints"] = (
                    [[.5, .5, .9]] * 17 if kind == "collapsed" else [[.5, .5, .1]] * 17)
            with self.subTest(kind=kind):
                self.assertNotIn('<svg', render_report(value))
                self.assertIn('Titik tubuh belum jelas', render_report(value))

    def test_rejects_invalid_coordinates_and_incomplete_or_image_exporting_result(self):
        for bad in (float("nan"), float("inf"), -1, 1.1, True, "0.5"):
            value = fixture()
            value["validation"]["pose"]["keypoints"][0][0] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                report_data(value)
        for change in ({"software_passed": False}, {"frames_per_burst": 1},
                       {"images_saved": True}, {"cloud_events_sent": True}, {"edge_service_restored": False}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                report_data({**fixture(), **change})

    def test_model_result_text_is_escaped_and_input_is_not_rewritten(self):
        value = fixture()
        value["validation"]["result"] = '<img src=x onerror="alert(1)">'
        original = copy.deepcopy(value)
        self.assertIn('&lt;img', render_report(value))
        self.assertNotIn('<img', render_report(value))
        self.assertEqual(value, original)


if __name__ == "__main__":
    unittest.main()
