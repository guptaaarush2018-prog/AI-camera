"""Lane zones: the map from pixels to traffic movements.

A detector says "a car, here". A signal controller needs "the left-turn lane on
the eastbound approach has five vehicles waiting". Zones are what closes that
gap, and they are drawn once at installation rather than inferred, because road
markings already encode the answer — a left-turn-only lane's queue *is* the
left-turn demand.

Zones live in a per-site JSON file (see config/int-04.example.json) so that
re-striping a junction is a config edit rather than a code change.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

# Passenger Car Units: how much junction capacity one vehicle consumes relative
# to a car. Standard traffic-engineering figures, overridable per site because
# they vary by country and geometry. Keys are detector class labels.
DEFAULT_PCU = {
    "bicycle": 0.2,
    "motorcycle": 0.4,
    "car": 1.0,
    "bus": 2.0,
    "truck": 2.0,
}

Point = tuple[float, float]


@dataclass(frozen=True)
class Zone:
    """One lane, and the movement its road markings permit."""

    name: str
    approach: str          # which arm of the junction: n / e / s / w
    movement: str          # left / through / right, or "left|through" if shared
    polygon: tuple[Point, ...]

    @property
    def shared(self) -> bool:
        """True for a lane that permits more than one movement.

        Demand for a shared lane is real but its split is not observable at the
        stop line — see ARCHITECTURE.md 4.3.
        """
        return "|" in self.movement

    @property
    def movements(self) -> tuple[str, ...]:
        return tuple(self.movement.split("|"))

    def contains(self, point: Point) -> bool:
        """Ray casting: count edge crossings to the right of the point."""
        x, y = point
        inside = False
        poly = self.polygon
        j = len(poly) - 1
        for i in range(len(poly)):
            xi, yi = poly[i]
            xj, yj = poly[j]
            # Half-open comparison, so a point exactly level with a shared
            # vertex is counted once rather than zero or twice.
            if (yi > y) != (yj > y):
                x_cross = xi + (y - yi) / (yj - yi) * (xj - xi)
                if x < x_cross:
                    inside = not inside
            j = i
        return inside

    def scaled(self, factor: tuple[float, float]) -> "Zone":
        fx, fy = factor
        return Zone(
            self.name, self.approach, self.movement,
            tuple((x * fx, y * fy) for x, y in self.polygon),
        )


class ZoneMap:
    """The zones for one camera, plus the site's PCU weights."""

    def __init__(
        self,
        zones: Iterable[Zone],
        frame_size: tuple[int, int],
        pcu: dict[str, float] | None = None,
        site: str = "",
    ):
        self.zones = list(zones)
        self.frame_size = frame_size      # what the polygons were drawn against
        self.pcu = {**DEFAULT_PCU, **(pcu or {})}
        self.site = site

    @classmethod
    def from_file(cls, path: str | Path) -> "ZoneMap":
        data = json.loads(Path(path).read_text())
        zones = [
            Zone(
                name=z["name"],
                approach=z["approach"],
                movement=z["movement"],
                polygon=tuple((float(x), float(y)) for x, y in z["polygon"]),
            )
            for z in data["zones"]
        ]
        size = tuple(data.get("frame_size", (1280, 720)))
        return cls(zones, (int(size[0]), int(size[1])),
                   data.get("pcu"), data.get("site", ""))

    def to_dict(self) -> dict[str, Any]:
        return {
            "site": self.site,
            "frame_size": list(self.frame_size),
            "pcu": self.pcu,
            "zones": [
                {"name": z.name, "approach": z.approach, "movement": z.movement,
                 "polygon": [list(p) for p in z.polygon]}
                for z in self.zones
            ],
        }

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2) + "\n")

    def scaled_to(self, display_size: tuple[int, int]) -> "ZoneMap":
        """Zones drawn against one resolution, used at another.

        Detections arrive in display coordinates, so a config drawn on a
        1280x720 still has to be stretched before it will line up with a
        pipeline running at a different size.
        """
        if tuple(display_size) == tuple(self.frame_size):
            return self
        fx = display_size[0] / self.frame_size[0]
        fy = display_size[1] / self.frame_size[1]
        return ZoneMap([z.scaled((fx, fy)) for z in self.zones],
                       display_size, self.pcu, self.site)

    def zone_for(self, point: Point) -> Zone | None:
        """The first zone containing `point`, or None if it is off-lane.

        Zones are expected not to overlap; if they do, declaration order wins.
        """
        for zone in self.zones:
            if zone.contains(point):
                return zone
        return None

    def pcu_for(self, label: str) -> float:
        """Unknown classes count as one car — the safe middle."""
        return self.pcu.get(label, 1.0)

    @property
    def approaches(self) -> list[str]:
        seen = []
        for z in self.zones:
            if z.approach not in seen:
                seen.append(z.approach)
        return seen

    def by_approach(self, approach: str) -> list[Zone]:
        return [z for z in self.zones if z.approach == approach]

    def __len__(self) -> int:
        return len(self.zones)
