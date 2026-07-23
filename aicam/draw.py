"""Box drawing for the preview window."""

import cv2
import numpy as np

from aicam.detection import Detection
from aicam.zones import ZoneMap

BOX_COLOR = (0, 255, 0)      # BGR
TEXT_COLOR = (255, 255, 255)
ZONE_COLOR = (0, 180, 255)
GROUND_COLOR = (0, 140, 255)


def draw_zones(frame: np.ndarray, zones: ZoneMap) -> None:
    """Outline each lane zone and label it, in place."""
    for zone in zones.zones:
        points = np.array([(int(x), int(y)) for x, y in zone.polygon], np.int32)
        cv2.polylines(frame, [points], True, ZONE_COLOR, 1)
        cv2.putText(
            frame, f"{zone.name} [{zone.movement}]",
            (int(points[:, 0].mean()) - 50, int(points[:, 1].max()) - 8),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, ZONE_COLOR, 1, cv2.LINE_AA,
        )


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
        if "zone" in det.extra:
            caption += f" @{det.extra['zone']}"

        # The point the object is assigned to a lane by. Drawing it makes a
        # mis-drawn zone boundary obvious instead of mysterious.
        gx, gy = det.ground
        cv2.circle(frame, (int(gx), int(gy)), 3, GROUND_COLOR, -1)

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
