"""Detector interface.

Anything that turns a frame into a list of Detections implements this. Keeping
the Hailo specifics behind it means a CPU/TFLite fallback or a different .hef
model is a one-line swap in main.py.
"""

from abc import ABC, abstractmethod
from typing import Any

from aicam.detection import Detection


class Detector(ABC):
    @property
    @abstractmethod
    def input_size(self) -> tuple[int, int]:
        """(width, height) the model wants. The camera feeds a stream this size."""

    @abstractmethod
    def detect(self, image: Any, frame_size: tuple[int, int]) -> list[Detection]:
        """Run inference on `image`.

        `frame_size` is the (width, height) that returned boxes should be scaled
        to, which is usually the display frame rather than the model input.
        """

    def close(self) -> None:
        """Release hardware. Default is a no-op."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
