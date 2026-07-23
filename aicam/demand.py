"""Queue length, arrival rate and turning counts, per lane.

This is the stage that turns tracked objects into the numbers a signal
controller actually consumes, and it is the last piece of Phase 1. Run it as a
processor *after* the Tracker — it needs stable IDs to tell an arrival from a
vehicle it has already counted, and speed to tell a queue from moving traffic.
"""

from collections import deque
from dataclasses import dataclass, field

from aicam.detection import Detection, Frame
from aicam.zones import Zone, ZoneMap

# See ARCHITECTURE.md 6.3. A saturated lane discharges roughly 1800 vehicles
# per hour of green — one every two seconds — after about two seconds of
# start-up lost time while the queue reacts to the change.
SATURATION_HEADWAY = 2.0
STARTUP_LOST_TIME = 2.0

# Below this many pixels per second an object counts as stopped. Pixels are a
# stand-in until a homography exists (ARCHITECTURE.md 4.3): the honest unit is
# metres per second, and this threshold has to be retuned per mounting.
STOPPED_BELOW_PX_S = 15.0

RATE_WINDOW_S = 60.0


@dataclass
class ZoneDemand:
    """What one lane currently looks like."""

    zone: Zone
    present: int = 0            # vehicles in the zone right now
    queue: int = 0              # of those, how many are stopped
    queue_pcu: float = 0.0      # the queue weighted by vehicle size
    total: int = 0              # unique vehicles since startup
    arrivals: deque = field(default_factory=deque)   # timestamps, recent only

    def rate_per_min(self, elapsed: float) -> float:
        """Arrivals per minute, given how long we have actually been watching."""
        if elapsed <= 0:
            return 0.0
        return len(self.arrivals) / elapsed * 60.0

    @property
    def clearance_seconds(self) -> float:
        """How much green this queue needs — the currency from 6.3.

        Seconds, not vehicles: it is what green time is measured in, and it
        already accounts for a lorry costing more of the junction than a car.
        """
        if self.queue == 0:
            return 0.0
        return STARTUP_LOST_TIME + self.queue_pcu * SATURATION_HEADWAY


class DemandMonitor:
    """Measures demand per lane, per approach, from tracked detections."""

    def __init__(
        self,
        zones: ZoneMap,
        stopped_below: float = STOPPED_BELOW_PX_S,
        window: float = RATE_WINDOW_S,
    ):
        self.zones = zones
        self.stopped_below = stopped_below
        self.window = window

        self.demand = {z.name: ZoneDemand(z) for z in zones.zones}
        self.now = 0.0
        # Rates divide by how long we have been watching, which is not the same
        # as the timestamp: the camera's clock starts at an arbitrary large
        # number, so dividing by `now` would report a rate of nearly zero.
        self.start: float | None = None
        # (zone name, track id) pairs already counted, so a vehicle sitting in
        # a queue for ninety seconds is one arrival rather than 2700.
        self._counted: set[tuple[str, int]] = set()

    def __call__(self, frame: Frame) -> None:
        self.update(frame.detections, frame.timestamp)

    @property
    def elapsed(self) -> float:
        """Seconds of observation, capped at the rate window."""
        if self.start is None:
            return 0.0
        return min(self.now - self.start, self.window)

    def update(self, detections: list[Detection], timestamp: float) -> None:
        self.now = timestamp
        if self.start is None:
            self.start = timestamp

        for d in self.demand.values():
            d.present = d.queue = 0
            d.queue_pcu = 0.0
            while d.arrivals and timestamp - d.arrivals[0] > self.window:
                d.arrivals.popleft()

        for det in detections:
            # The ground-contact point, not the box centre: at an angle the
            # middle of a lorry sits over the next lane along.
            zone = self.zones.zone_for(det.ground)
            if zone is None:
                continue

            det.extra["zone"] = zone.name
            det.extra["approach"] = zone.approach
            det.extra["movement"] = zone.movement

            track_id = det.extra.get("track_id")
            # The tracker's min_hits exists to reject single-frame false
            # positives; demand has to honour it, or a flicker becomes a
            # vehicle in the counts. Without a tracker, take what we are given.
            if track_id is not None and not det.extra.get("confirmed", False):
                continue

            d = self.demand[zone.name]
            d.present += 1

            if track_id is not None:
                key = (zone.name, track_id)
                if key not in self._counted:
                    self._counted.add(key)
                    d.total += 1
                    d.arrivals.append(timestamp)

            if det.extra.get("speed", 0.0) < self.stopped_below:
                d.queue += 1
                d.queue_pcu += self.zones.pcu_for(det.label)

    # ── Per-approach roll-ups ───────────────────────────────────────────
    def by_approach(self, approach: str) -> list[ZoneDemand]:
        return [self.demand[z.name] for z in self.zones.by_approach(approach)]

    def queue(self, approach: str) -> int:
        return sum(d.queue for d in self.by_approach(approach))

    def rate(self, approach: str) -> float:
        return sum(d.rate_per_min(self.elapsed) for d in self.by_approach(approach))

    def clearance_seconds(self, approach: str) -> float:
        """Green needed to clear this approach — the longest of its lanes.

        Lanes discharge in parallel, so an approach is ready when its slowest
        lane is, not when the sum of them would be.
        """
        return max((d.clearance_seconds for d in self.by_approach(approach)), default=0.0)

    def turning_split(self, approach: str) -> dict[str, float]:
        """Observed share of each movement, learned from what vehicles did.

        Dedicated lanes only — a shared lane cannot tell you which way its
        vehicles intended to go, so including it would invent a number. This is
        the self-updating turning-movement count from ARCHITECTURE.md 4.3.
        """
        counts: dict[str, int] = {}
        for d in self.by_approach(approach):
            if not d.zone.shared:
                counts[d.zone.movement] = counts.get(d.zone.movement, 0) + d.total
        total = sum(counts.values())
        if not total:
            return {}
        return {move: n / total for move, n in sorted(counts.items())}

    def snapshot(self) -> dict:
        """The state this node would publish — see ARCHITECTURE.md 5.

        Rates are vehicles per minute.
        """
        return {
            "node": self.zones.site or "unknown",
            "t": round(self.now, 2),
            "queue": {a: self.queue(a) for a in self.zones.approaches},
            "rate": {a: round(self.rate(a), 1) for a in self.zones.approaches},
            "clearance_s": {
                a: round(self.clearance_seconds(a), 1) for a in self.zones.approaches
            },
            "health": "ok",
        }
