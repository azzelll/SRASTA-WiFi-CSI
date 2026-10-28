"""One event-only burst using OS Picamera2; emit RGB pixels through stdout.

No images/keypoints are written to disk or exposed over a network.
"""
from __future__ import annotations

import argparse
import sys
import time


def movenet_image(rgb):
    """Correct the upside-down mount, then letterbox the full camera view."""
    from PIL import Image, ImageOps
    image = Image.fromarray(rgb).transpose(Image.Transpose.ROTATE_180)
    return ImageOps.pad(image, (192, 192), method=Image.Resampling.BILINEAR, color=(0, 0, 0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, choices=(1, 3), default=1)
    args = parser.parse_args()
    from picamera2 import Picamera2
    camera = Picamera2()
    started = False
    try:
        # Picamera2 BGR888 supplies RGB byte order to capture_array (libcamera naming).
        camera.configure(camera.create_still_configuration(main={"size": (640, 480), "format": "BGR888"}))
        camera.start()
        started = True
        time.sleep(1.0)  # Allow exposure/white balance to settle after sensor activation.
        for index in range(args.frames):
            if index:
                time.sleep(.3)
            image = movenet_image(camera.capture_array())
            sys.stdout.buffer.write(image.tobytes())
        sys.stdout.buffer.flush()
    finally:
        if started:
            camera.stop()
        camera.close()


if __name__ == "__main__":
    main()
