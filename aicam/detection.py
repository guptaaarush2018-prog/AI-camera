"""Core data types shared by every detector and processor."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Detection:
    """One detected object in one frame.

    Coordinates are absolute pixels in the frame the detector was given,
    with (0, 0) at the top-left.
    """

    label: str
    score: float
    x0: int
    y0: int
    x1: int
    y1: int
    # Populated by later stages (tracking, velocity) without changing this schema.
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)

    @property
    def ground(self) -> tuple[float, float]:
        """Bottom-centre — roughly where the object meets the road.

        The anchor for anything spatial: which lane it is in, how far back the
        queue reaches, how fast it is travelling. The box centre floats around
        a vehicle's windscreen, drifts across lane boundaries when the approach
        is viewed at an angle, and moves on its own as perspective grows the
        box. This point does none of that.
        """
        return ((self.x0 + self.x1) / 2, float(self.y1))


@dataclass
class Frame:
    """A frame plus everything derived from it, passed down the processor chain."""

    image: Any                      # numpy array, RGB — what the detector ran on
    index: int                      # monotonic frame counter
    timestamp: float                # time.monotonic() when captured
    detections: list[Detection] = field(default_factory=list)
    display: Any = None              # full-res BGR array, only captured if requested
