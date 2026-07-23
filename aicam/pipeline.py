"""Camera capture loop and the processor chain that runs on every frame."""

import time
from abc import ABC, abstractmethod
from typing import Callable, Iterator

import numpy as np
from libcamera import Transform
from picamera2 import Picamera2

from aicam.detection import Frame
from aicam.detectors.base import Detector

# A processor sees each frame after detection and may annotate it in place
# (assign IDs, compute velocity, trigger an alert). Add them in main.py.
Processor = Callable[[Frame], None]


class FramePipeline(ABC):
    """What every frame source has in common: run the detector, then the
    processor chain, on images from wherever.

    Subclasses supply `frames()`. Everything downstream — tracking, zones,
    drawing — sees the same `Frame` whether it came from the camera or a file,
    which is what makes detection testable without hardware.
    """

    def __init__(
        self,
        detector: Detector,
        display_size: tuple[int, int] = (1280, 720),
        processors: list[Processor] | None = None,
    ):
        self.detector = detector
        self.display_size = display_size
        self.processors = processors or []

    def _detect(self, image, index: int, timestamp: float) -> Frame:
        """Build a frame and attach detections, scaled to `display_size`."""
        frame = Frame(image=image, index=index, timestamp=timestamp)
        frame.detections = self.detector.detect(image, self.display_size)
        return frame

    def _run_processors(self, frame: Frame) -> None:
        """Run last, so processors can see the display image if one was set."""
        for processor in self.processors:
            processor(frame)

    @abstractmethod
    def frames(self, want_display: bool = False) -> Iterator[Frame]:
        """Yield frames with detections and processor output attached."""

    def start(self) -> None:
        """Begin capture. Default is a no-op."""

    def stop(self) -> None:
        """Release the source. Default is a no-op."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()
        self.detector.close()


class CameraPipeline(FramePipeline):
    """Drives Picamera2 with two streams: a display-res `main` and a
    model-res `lores` that inference runs on, so we never pay to downscale
    a big frame in Python.
    """

    def __init__(
        self,
        detector: Detector,
        display_size: tuple[int, int] = (1280, 720),
        processors: list[Processor] | None = None,
    ):
        super().__init__(detector, display_size, processors)

        model_w, model_h = detector.input_size
        self.picam2 = Picamera2()
        config = self.picam2.create_preview_configuration(
            main={"size": display_size, "format": "XRGB8888"},
            lores={"size": (model_w, model_h), "format": "RGB888"},
            controls={"FrameRate": 30},
            # Flip the sensor vertically in hardware so callers don't have to
            # (and neither the display nor the model sees an upside-down frame).
            transform=Transform(vflip=1),
        )
        self.picam2.configure(config)

    def start(self) -> None:
        self.picam2.start()

    def stop(self) -> None:
        self.picam2.stop()
        self.picam2.close()

    def frames(self, want_display: bool = False) -> Iterator[Frame]:
        """Yield frames with detections attached, indefinitely.

        `want_display` also captures the full-res `main` stream as BGR (the
        XRGB8888 buffer's first three channels are already B, G, R) — skipped
        by default since headless callers never touch it.
        """
        index = 0
        while True:
            lores = self.picam2.capture_array("lores")
            frame = self._detect(lores, index, time.monotonic())

            if want_display:
                # Slicing off the X channel leaves a non-contiguous view;
                # cv2 drawing needs a contiguous C-array, so copy it.
                main = self.picam2.capture_array("main")[:, :, :3]
                frame.display = np.ascontiguousarray(main)

            self._run_processors(frame)
            yield frame
            index += 1

    def __enter__(self):
        # Camera isn't started here: a preview (if any) must be started on the
        # unstarted Picamera2 first, or Picamera2 raises "event loop already
        # running". Call start() explicitly once the preview is set up.
        return self
