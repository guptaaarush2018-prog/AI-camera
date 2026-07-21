"""Box overlay for the preview window."""

import cv2
import numpy as np

from aicam.detection import Detection

BOX_COLOR = (0, 255, 0, 255)   # RGBA
TEXT_COLOR = (255, 255, 255, 255)


def make_overlay(
    detections: list[Detection], size: tuple[int, int]
) -> np.ndarray:
    """Build a transparent RGBA layer for Picamera2's set_overlay()."""
    width, height = size
    overlay = np.zeros((height, width, 4), dtype=np.uint8)

    for det in detections:
        cv2.rectangle(overlay, (det.x0, det.y0), (det.x1, det.y1), BOX_COLOR, 2)

        caption = f"{det.label} {det.score:.2f}"
        # Velocity and any other processor output tags along automatically.
        if "speed" in det.extra:
            caption += f" {det.extra['speed']:.1f}px/s"

        cv2.putText(
            overlay,
            caption,
            (det.x0 + 4, max(det.y0 - 6, 12)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            TEXT_COLOR,
            1,
            cv2.LINE_AA,
        )

    return overlay
