"""Read frames from a video file instead of the camera.

Two reasons this exists. It makes detection **repeatable** — a live camera run
is slow to iterate on and never twice the same, so nothing about the detector
can be regression-tested against it. And it is the first step of the demand
study: run the detector over footage of a real junction to measure when
vehicles actually arrived, what they were, and which way they went.

Everything downstream is unchanged. A `Frame` from here is the same object the
camera produces, so the tracker, zones and drawing cannot tell the difference.
"""

import time
from pathlib import Path
from typing import Iterator

import cv2

from aicam.detection import Frame
from aicam.detectors.base import Detector
from aicam.pipeline import FramePipeline, Processor

DEFAULT_FPS = 30.0


class VideoPipeline(FramePipeline):
    """Plays a video file through the detector and processor chain."""

    def __init__(
        self,
        path: str,
        detector: Detector,
        display_size: tuple[int, int] | None = None,
        processors: list[Processor] | None = None,
        realtime: bool = False,
        loop: bool = False,
    ):
        """
        `display_size` defaults to the video's own resolution — detections are
        scaled to it, so it is the coordinate space every later stage works in.
        `realtime` paces playback to the file's frame rate for a live demo;
        leave it off to process as fast as the accelerator allows.
        """
        if not Path(path).exists():
            raise FileNotFoundError(f"No video at {path}")

        self.path = path
        self.capture = cv2.VideoCapture(path)
        if not self.capture.isOpened():
            raise RuntimeError(f"Could not open {path} — unsupported codec?")

        native = (
            int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )
        super().__init__(detector, display_size or native, processors)

        self.native_size = native
        self.realtime = realtime
        self.loop = loop

        # Some containers report 0 or nan rather than admitting they don't know.
        fps = self.capture.get(cv2.CAP_PROP_FPS)
        self.fps = fps if fps and fps == fps and fps > 0 else DEFAULT_FPS

        self.frame_count = int(self.capture.get(cv2.CAP_PROP_FRAME_COUNT)) or 0

    @property
    def duration(self) -> float:
        """Length in seconds, or 0 if the container didn't say."""
        return self.frame_count / self.fps if self.frame_count else 0.0

    def frames(self, want_display: bool = False) -> Iterator[Frame]:
        """Yield frames until the file ends (or forever, if `loop`)."""
        model_size = self.detector.input_size
        index = 0
        started = time.monotonic()

        while True:
            ok, bgr = self.capture.read()
            if not ok:
                if not self.loop:
                    return
                self.capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, bgr = self.capture.read()
                if not ok:
                    return

            # Squashed to the model's input, not letterboxed, because that is
            # what the camera path does: Picamera2 scales the whole field of
            # view into the lores stream. Matching it keeps box coordinates
            # meaning the same thing from both sources.
            #
            # Channel order also matches: OpenCV decodes to BGR, and
            # Picamera2's "RGB888" lores stream is documented as blue, green,
            # red in memory. Both paths therefore hand the model the same
            # order, whatever the model would have preferred.
            model_image = cv2.resize(bgr, model_size, interpolation=cv2.INTER_AREA)

            # Video time, not wall-clock. The tracker divides by the gap between
            # timestamps to get speed, so using the clock would make every
            # measurement depend on how fast the machine happened to decode.
            timestamp = index / self.fps
            frame = self._detect(model_image, index, timestamp)

            if want_display:
                frame.display = (
                    bgr if self.native_size == self.display_size
                    else cv2.resize(bgr, self.display_size)
                )

            self._run_processors(frame)

            if self.realtime:
                ahead = timestamp - (time.monotonic() - started)
                if ahead > 0:
                    time.sleep(ahead)

            yield frame
            index += 1

    def stop(self) -> None:
        self.capture.release()
