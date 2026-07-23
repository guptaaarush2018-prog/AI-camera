"""Offline check for aicam.video — no camera, no Hailo.

Builds a short video of a bright square moving left to right, then runs it
through VideoPipeline with a detector that finds the square by thresholding.
That exercises the real decode, resize and coordinate-scaling path.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

from aicam.detection import Detection
from aicam.detectors.base import Detector
from aicam.tracking import Tracker
from aicam.video import VideoPipeline

W, H, FPS, N = 640, 360, 25, 50
BOX = 40


class SquareFinder(Detector):
    """Finds the brightest blob and reports it, scaled to the frame size."""

    @property
    def input_size(self):
        return (320, 320)          # deliberately not the video's size

    def detect(self, image, frame_size):
        grey = image[:, :, 0] if image.ndim == 3 else image
        ys, xs = np.where(grey > 200)
        if len(xs) == 0:
            return []
        mh, mw = grey.shape[:2]
        fw, fh = frame_size
        return [Detection(
            label="car", score=0.9,
            x0=int(xs.min() / mw * fw), y0=int(ys.min() / mh * fh),
            x1=int(xs.max() / mw * fw), y1=int(ys.max() / mh * fh),
        )]


def make_video(path):
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), FPS, (W, H))
    assert writer.isOpened(), "OpenCV cannot write MJPG/AVI here"
    for i in range(N):
        frame = np.zeros((H, W, 3), np.uint8)
        x = 40 + i * 10
        cv2.rectangle(frame, (x, 150), (x + BOX, 150 + BOX), (255, 255, 255), -1)
        writer.write(frame)
    writer.release()


tmp = tempfile.mkdtemp()
video = str(Path(tmp) / "moving.avi")
make_video(video)
print(f"1. wrote {N} frames of {W}x{H} @ {FPS} fps  OK")

# 2. Metadata is read back off the container.
det = SquareFinder()
pipe = VideoPipeline(video, det)
assert pipe.native_size == (W, H), pipe.native_size
assert abs(pipe.fps - FPS) < 0.01, pipe.fps
assert pipe.display_size == (W, H), pipe.display_size
print(f"2. metadata: {pipe.native_size} @ {pipe.fps} fps, "
      f"{pipe.duration:.1f}s  OK")

# 3. It plays to the end and stops — no infinite loop, no hang.
frames = list(pipe.frames())
assert len(frames) == N, f"got {len(frames)} frames, expected {N}"
pipe.stop()
print(f"3. played {len(frames)} frames and stopped cleanly  OK")

# 4. Timestamps are video time, not wall-clock. This is what keeps speed
#    measurements independent of how fast the machine decodes.
assert frames[0].timestamp == 0.0
assert abs(frames[10].timestamp - 10 / FPS) < 1e-9, frames[10].timestamp
assert abs(frames[-1].timestamp - (N - 1) / FPS) < 1e-9
print(f"4. frame 10 at t={frames[10].timestamp:.3f}s (= 10/{FPS})  OK")

# 5. The detector saw the model's input size, and boxes came back in display
#    coordinates rather than model coordinates.
assert frames[0].image.shape[:2] == (320, 320), frames[0].image.shape
assert all(len(f.detections) == 1 for f in frames), "square lost on some frame"
first, last = frames[0].detections[0], frames[-1].detections[0]
assert first.x0 < last.x0, "square should have moved right"
assert last.x1 <= W, f"box {last.x1} outside display width {W}"
print(f"5. model got 320x320; box moved x={first.x0}->{last.x0} "
      f"within 0..{W}  OK")

# 6. A tracker as a processor holds one ID across the whole clip.
tracker = Tracker()
pipe = VideoPipeline(video, SquareFinder(), processors=[tracker])
seen = [f.detections[0].extra.get("track_id") for f in pipe.frames()]
pipe.stop()
assert set(seen) == {1}, f"expected one track, saw {sorted(set(seen))}"
assert tracker.counts == {"car": 1}, tracker.counts
speed = tracker.tracks[0].speed()
print(f"6. one track across {len(seen)} frames, counts={tracker.counts}, "
      f"speed={speed:.0f}px/s  OK")

# 7. display_size overrides scale the boxes without touching the model input.
pipe = VideoPipeline(video, SquareFinder(), display_size=(1280, 720))
f = next(pipe.frames(want_display=True))
pipe.stop()
assert f.display.shape[:2] == (720, 1280), f.display.shape
assert f.detections[0].x1 <= 1280
print(f"7. display 1280x720, box scaled to x1={f.detections[0].x1}  OK")

# 8. Looping keeps yielding past the end of the file.
pipe = VideoPipeline(video, SquareFinder(), loop=True)
it = pipe.frames()
count = sum(1 for _ in zip(range(N + 15), it))
pipe.stop()
assert count == N + 15, count
print(f"8. loop=True yielded {count} frames from a {N}-frame file  OK")

# 9. A missing file fails immediately and says so.
try:
    VideoPipeline("/nonexistent/clip.mp4", SquareFinder())
    raise AssertionError("should have raised")
except FileNotFoundError:
    print("9. missing file raises FileNotFoundError  OK")

print("\nAll video checks passed.")
