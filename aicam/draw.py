"""Box drawing for the preview window."""

import cv2
import numpy as np

from aicam.detection import Detection

BOX_COLOR = (0, 255, 0)      # BGR
TEXT_COLOR = (255, 255, 255)


def draw_detections(frame: np.ndarray, detections: list[Detection]) -> None:
    """Draw boxes and captions directly onto a BGR frame, in place."""
    for det in detections:
        cv2.rectangle(frame, (det.x0, det.y0), (det.x1, det.y1), BOX_COLOR, 2)

        caption = f"{det.label} {det.score:.2f}"
        # Processor output tags along automatically; none of it is required.
        if "track_id" in det.extra:
            caption = f"#{det.extra['track_id']} " + caption
        if det.extra.get("speed"):
            caption += f" {det.extra['speed']:.0f}px/s"
        if "heading" in det.extra:
            caption += f" {det.extra['heading']}"

        cv2.putText(
            frame,
            caption,
            (det.x0 + 4, max(det.y0 - 6, 12)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            TEXT_COLOR,
            1,
            cv2.LINE_AA,
        )
