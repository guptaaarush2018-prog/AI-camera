"""Hailo-8/8L detector via Picamera2's bundled HailoRT wrapper."""

from pathlib import Path
from typing import Any

from picamera2.devices import Hailo

from aicam.detection import Detection
from aicam.detectors.base import Detector

# yolov8s is what `hailo-all` ships and runs at ~30 fps on the 8L. Traffic only
# needs ~10, so there is room to trade that headroom for accuracy: drop in a
# yolov8m_h8l.hef via --model for +5.3 mAP at ~half the frame rate (still well
# above 10). yolov8l goes too far — it falls under the 10 fps floor. See the
# "Upgrading the detector model" note in CLAUDE.md. Nothing else has to change:
# the detector reads the model's own input shape and scales boxes to the frame.
DEFAULT_MODEL = "/usr/share/hailo-models/yolov8s_h8l.hef"
DEFAULT_LABELS = "/usr/share/hailo-models/coco.txt"


class HailoDetector(Detector):
    """Wraps a compiled .hef network.

    The stock yolov8 .hef files do NMS on-chip, so `Hailo.run` gives back one
    list per class, each entry [y0, x0, y1, x1, score] in 0..1 normalized
    coordinates. Anything without on-chip NMS would need its own postprocess.
    """

    def __init__(
        self,
        model_path: str = DEFAULT_MODEL,
        labels_path: str | None = DEFAULT_LABELS,
        threshold: float = 0.5,
    ):
        if not Path(model_path).exists():
            raise FileNotFoundError(
                f"No .hef model at {model_path}. Install the stock models with "
                "'sudo apt install hailo-all', or pass --model."
            )

        self.threshold = threshold
        self.hailo = Hailo(model_path)
        model_h, model_w, _ = self.hailo.get_input_shape()
        self._input_size = (model_w, model_h)
        self.labels = self._load_labels(labels_path)

    @staticmethod
    def _load_labels(labels_path: str | None) -> list[str]:
        if labels_path and Path(labels_path).exists():
            return Path(labels_path).read_text().splitlines()
        # Fall back to numeric class names rather than failing outright.
        return []

    def _label_for(self, class_id: int) -> str:
        if class_id < len(self.labels):
            return self.labels[class_id]
        return f"class_{class_id}"

    @property
    def input_size(self) -> tuple[int, int]:
        return self._input_size

    def detect(self, image: Any, frame_size: tuple[int, int]) -> list[Detection]:
        raw = self.hailo.run(image)
        width, height = frame_size

        detections: list[Detection] = []
        for class_id, class_detections in enumerate(raw):
            for det in class_detections:
                score = float(det[4])
                if score < self.threshold:
                    continue
                y0, x0, y1, x1 = det[:4]
                detections.append(
                    Detection(
                        label=self._label_for(class_id),
                        score=score,
                        x0=int(x0 * width),
                        y0=int(y0 * height),
                        x1=int(x1 * width),
                        y1=int(y1 * height),
                    )
                )
        return detections

    def close(self) -> None:
        self.hailo.close()
