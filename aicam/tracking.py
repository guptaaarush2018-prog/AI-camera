"""Multi-object tracking: turns per-frame detections into persistent objects.

A detector answers "what is in this frame". Everything downstream — counts that
don't double-count, speed, direction of travel, queue length — needs "is this
the same car as last frame", which is what this module adds.

The association is greedy IoU matching within a label. That is deliberate: a
Kalman/Hungarian tracker buys accuracy under heavy occlusion, and at 30 fps on a
fixed camera, objects move a few pixels per frame and overlap their previous box
almost every time. Simple is enough here, and simple is auditable.
"""

import math
import time
from collections import deque
from dataclasses import dataclass, field

from aicam.detection import Detection, Frame

# Compass points at 45 degree intervals, starting at "up the screen" and going
# clockwise. Screen-relative, not geographic: mounting decides what "N" means.
_COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def iou(a: Detection, b: "Track") -> float:
    """Intersection over union of a detection and a track's last known box."""
    bx0, by0, bx1, by1 = b.box
    ix0, iy0 = max(a.x0, bx0), max(a.y0, by0)
    ix1, iy1 = min(a.x1, bx1), min(a.y1, by1)

    iw, ih = ix1 - ix0, iy1 - iy0
    if iw <= 0 or ih <= 0:
        return 0.0

    intersection = iw * ih
    union = a.width * a.height + (bx1 - bx0) * (by1 - by0) - intersection
    return intersection / union if union > 0 else 0.0


@dataclass
class Track:
    """One object followed across frames."""

    id: int
    label: str
    box: tuple[int, int, int, int]
    score: float
    # (timestamp, (cx, cy)) samples, oldest first. Bounded so a track that
    # lives for an hour doesn't grow without limit.
    history: deque = field(default_factory=lambda: deque(maxlen=90))
    hits: int = 1            # frames this track was matched in
    misses: int = 0          # consecutive frames since the last match
    confirmed: bool = False
    last_update: float = 0.0  # timestamp of the last frame this track saw

    @property
    def center(self) -> tuple[float, float]:
        x0, y0, x1, y1 = self.box
        return ((x0 + x1) / 2, (y0 + y1) / 2)

    def _displacement(self, window: float) -> tuple[float, float, float]:
        """(dx, dy, dt) over roughly the last `window` seconds of history."""
        if len(self.history) < 2:
            return 0.0, 0.0, 0.0

        newest_t, (x1, y1) = self.history[-1]
        oldest_t, (x0, y0) = self.history[0]
        # Walk forward to the first sample inside the window, so a long-lived
        # track reports current speed rather than its lifetime average.
        for t, (x, y) in self.history:
            if newest_t - t <= window:
                oldest_t, x0, y0 = t, x, y
                break

        return x1 - x0, y1 - y0, newest_t - oldest_t

    def velocity(self, window: float = 0.5) -> tuple[float, float]:
        """(vx, vy) in pixels per second over the last `window` seconds."""
        dx, dy, dt = self._displacement(window)
        if dt <= 0:
            return 0.0, 0.0
        return dx / dt, dy / dt

    def coast(self, dt: float) -> None:
        """Advance the box along its last known velocity for `dt` seconds.

        Used only while a track is unmatched. Without it, a car doing 300 px/s
        that vanishes behind a van for ten frames re-emerges 100 px from its
        last box, overlaps nothing, and is counted as a second car.

        The history is deliberately left alone: these are guesses, and letting
        them feed the speed estimate would make it self-confirming.
        """
        vx, vy = self.velocity()
        x0, y0, x1, y1 = self.box
        ox, oy = round(vx * dt), round(vy * dt)
        self.box = (x0 + ox, y0 + oy, x1 + ox, y1 + oy)

    def speed(self, window: float = 0.5) -> float:
        """Pixels per second, averaged over the last `window` seconds.

        Pixels, not metres: converting needs a homography from the camera's
        mounting geometry, which is a calibration step this doesn't assume.
        """
        dx, dy, dt = self._displacement(window)
        if dt <= 0:
            return 0.0
        return math.hypot(dx, dy) / dt

    def heading(self, window: float = 0.5, min_travel: float = 8.0) -> str | None:
        """Compass direction of travel, or None if the object is basically still.

        `min_travel` in pixels suppresses the jitter of a stationary object's
        box, which would otherwise spin through all eight directions.
        """
        dx, dy, _ = self._displacement(window)
        if math.hypot(dx, dy) < min_travel:
            return None

        # Screen y grows downward, so negate it to make "up" mean north.
        angle = math.degrees(math.atan2(dx, -dy)) % 360
        return _COMPASS[round(angle / 45) % 8]


class Tracker:
    """A pipeline processor that assigns stable IDs to detections.

    Drop it into `CameraPipeline(processors=[...])`. It annotates each
    detection's `extra` in place and keeps its own list of live tracks, which is
    what queue-length and arrival-rate stages read.
    """

    def __init__(
        self,
        iou_threshold: float = 0.3,
        max_misses: int = 15,
        min_hits: int = 3,
    ):
        """
        `max_misses` is how many frames a track survives unmatched — at 30 fps,
        15 frames is half a second of occlusion behind a passing van.
        `min_hits` is how many frames it must be seen in before it counts, which
        is what keeps a single-frame false positive out of the totals.
        """
        self.iou_threshold = iou_threshold
        self.max_misses = max_misses
        self.min_hits = min_hits

        self.tracks: list[Track] = []
        # Unique objects seen since startup, per label. Incremented once, when a
        # track is confirmed — this is the number that means "12 cars", and it
        # never double-counts a car that was briefly occluded.
        self.counts: dict[str, int] = {}
        self._next_id = 1

    def __call__(self, frame: Frame) -> None:
        self.update(frame.detections, frame.timestamp)

    def update(
        self,
        detections: list[Detection],
        timestamp: float | None = None,
    ) -> list[Track]:
        """Match `detections` to existing tracks and return the live ones."""
        now = time.monotonic() if timestamp is None else timestamp

        matches = self._associate(detections)

        for det, track in matches:
            track.box = (det.x0, det.y0, det.x1, det.y1)
            track.score = det.score
            track.hits += 1
            track.misses = 0
            track.last_update = now
            track.history.append((now, det.ground))
            if not track.confirmed and track.hits >= self.min_hits:
                track.confirmed = True
                self.counts[track.label] = self.counts.get(track.label, 0) + 1

        matched_tracks = {id(track) for _, track in matches}
        for track in self.tracks:
            if id(track) not in matched_tracks:
                track.misses += 1
                track.coast(now - track.last_update)
                track.last_update = now

        matched_dets = {id(det) for det, _ in matches}
        for det in detections:
            if id(det) not in matched_dets:
                self.tracks.append(self._new_track(det, now))

        self.tracks = [t for t in self.tracks if t.misses <= self.max_misses]

        for det, track in matches:
            self._annotate(det, track)

        return self.tracks

    def _associate(
        self, detections: list[Detection]
    ) -> list[tuple[Detection, Track]]:
        """Greedy IoU matching: the most confident pairing wins, then the next."""
        candidates = []
        for det in detections:
            for track in self.tracks:
                if track.label != det.label:
                    continue
                overlap = iou(det, track)
                if overlap >= self.iou_threshold:
                    candidates.append((overlap, det, track))

        # Sort on overlap alone; the detections and tracks in the tuple are
        # never compared, which they can't be (neither defines an ordering).
        candidates.sort(key=lambda c: c[0], reverse=True)

        matches: list[tuple[Detection, Track]] = []
        taken_dets: set[int] = set()
        taken_tracks: set[int] = set()
        for _, det, track in candidates:
            if id(det) in taken_dets or id(track) in taken_tracks:
                continue
            matches.append((det, track))
            taken_dets.add(id(det))
            taken_tracks.add(id(track))
        return matches

    def _new_track(self, det: Detection, now: float) -> Track:
        track = Track(
            id=self._next_id,
            label=det.label,
            box=(det.x0, det.y0, det.x1, det.y1),
            score=det.score,
            last_update=now,
        )
        track.history.append((now, det.ground))
        self._next_id += 1
        self._annotate(det, track)
        return track

    @staticmethod
    def _annotate(det: Detection, track: Track) -> None:
        det.extra["track_id"] = track.id
        # Lets later stages honour min_hits instead of trusting every blip.
        det.extra["confirmed"] = track.confirmed
        det.extra["speed"] = track.speed()
        heading = track.heading()
        if heading:
            det.extra["heading"] = heading

    @property
    def confirmed_tracks(self) -> list[Track]:
        """Live tracks seen often enough to be believed."""
        return [t for t in self.tracks if t.confirmed]
