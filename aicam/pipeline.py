"""Camera capture loop and the processor chain that runs on every frame."""

import time
from typing import Callable, Iterator

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
        )
        self.picam2.configure(config)

    def start(self) -> None:
        self.picam2.start()

    def stop(self) -> None:
        self.picam2.stop()
        self.picam2.close()

    def frames(self) -> Iterator[Frame]:
        """Yield frames with detections attached, indefinitely."""
        index = 0
        while True:
            lores = self.picam2.capture_array("lores")
            frame = Frame(
                image=lores,
                index=index,
                timestamp=time.monotonic(),
            )
            frame.detections = self.detector.detect(lores, self.display_size)

            for processor in self.processors:
                processor(frame)

            yield frame
            index += 1

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()
        self.detector.close()
