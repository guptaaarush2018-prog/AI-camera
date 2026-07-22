"""Camera capture loop and the processor chain that runs on every frame."""

import time
from typing import Callable, Iterator

import numpy as np
from libcamera import Transform
from picamera2 import Picamera2

from aicam.detection import Frame
from aicam.detectors.base import Detector

# A processor sees each frame after detection and may annotate it in place
# (assign IDs, compute velocity, trigger an alert). Add them in main.py.
Processor = Callable[[Frame], None]


class CameraPipeline:
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
        self.detector = detector
        self.display_size = display_size
        self.processors = processors or []

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
            frame = Frame(
                image=lores,
                index=index,
                timestamp=time.monotonic(),
            )
            frame.detections = self.detector.detect(lores, self.display_size)

            if want_display:
                # Slicing off the X channel leaves a non-contiguous view;
                # cv2 drawing needs a contiguous C-array, so copy it.
                main = self.picam2.capture_array("main")[:, :, :3]
                frame.display = np.ascontiguousarray(main)

            for processor in self.processors:
                processor(frame)

            yield frame
            index += 1

    def __enter__(self):
        # Camera isn't started here: a preview (if any) must be started on the
        # unstarted Picamera2 first, or Picamera2 raises "event loop already
        # running". Call start() explicitly once the preview is set up.
        return self

    def __exit__(self, *exc):
        self.stop()
        self.detector.close()
