"""Image preparation runs in OS Python, separately from the inference venv."""
import unittest

import numpy as np

from srasta_csi.camera_capture import movenet_image


class CameraCaptureTests(unittest.TestCase):
    def test_rotated_mount_preserves_full_view_and_rgb_channel_order(self):
        rgb = np.zeros((480, 640, 3), dtype=np.uint8)
        rgb[:, :, 0] = 255
        image = np.asarray(movenet_image(rgb))
        self.assertEqual(image.shape, (192, 192, 3))
        self.assertEqual(image[0].max(), 0)
        self.assertEqual(image[23].max(), 0)
        np.testing.assert_array_equal(image[24, 0], [255, 0, 0])
        np.testing.assert_array_equal(image[167, -1], [255, 0, 0])
        self.assertEqual(image[168].max(), 0)
        # Distinct corners verify a 180-degree rotation, not a single-axis mirror.
        rgb[:240, :320] = [255, 0, 0]
        rgb[:240, 320:] = [0, 255, 0]
        rgb[240:, :320] = [0, 0, 255]
        rgb[240:, 320:] = [255, 255, 0]
        image = np.asarray(movenet_image(rgb))
        np.testing.assert_array_equal(image[60, 48], [255, 255, 0])
        np.testing.assert_array_equal(image[60, 144], [0, 0, 255])
        np.testing.assert_array_equal(image[132, 48], [0, 255, 0])
        np.testing.assert_array_equal(image[132, 144], [255, 0, 0])


if __name__ == "__main__":
    unittest.main()
