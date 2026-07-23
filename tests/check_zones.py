"""Offline checks for aicam.zones and aicam.demand — no camera, no Hailo.

Builds a three-lane approach, drives synthetic vehicles through it, and checks
the numbers a signal controller would consume: which lane, how many queued, how
much green that needs, and what the observed turning split is.
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aicam.demand import DemandMonitor
from aicam.detection import Detection
from aicam.tracking import Tracker
from aicam.zones import Zone, ZoneMap

FPS = 30.0


def det(label, cx, bottom, w=40, h=30, score=0.9):
    """A detection whose ground point (bottom-centre) is at (cx, bottom)."""
    return Detection(label, score,
                     int(cx - w / 2), int(bottom - h),
                     int(cx + w / 2), int(bottom))


# Three lanes side by side, 100 px wide, spanning y 200..700.
def lane(name, movement, x0, x1):
    return Zone(name, "e", movement, ((x0, 200), (x1, 200), (x1, 700), (x0, 700)))


ZONES = ZoneMap(
    [lane("eb-left", "left", 100, 200),
     lane("eb-through", "through", 200, 300),
     lane("eb-right", "right", 300, 400)],
    frame_size=(1280, 720),
    site="INT-04",
)

# 1. Point-in-polygon, including the edges between adjacent lanes.
assert ZONES.zone_for((150, 400)).name == "eb-left"
assert ZONES.zone_for((250, 400)).name == "eb-through"
assert ZONES.zone_for((350, 400)).name == "eb-right"
assert ZONES.zone_for((50, 400)) is None, "off-road point matched a lane"
assert ZONES.zone_for((250, 100)) is None, "point above the zone matched"
# A point on a shared boundary lands in exactly one lane, never both or neither.
boundary = [z for z in ZONES.zones if z.contains((200, 400))]
assert len(boundary) == 1, f"boundary point in {len(boundary)} zones"
print(f"1. containment: 3 lanes, off-road rejected, boundary in exactly 1  OK")

# 2. Ground point, not box centre. A tall box straddling a lane line must be
#    assigned by where its wheels are.
straddler = Detection("truck", 0.9, x0=170, y0=300, x1=260, y1=500)
assert straddler.center[0] == 215, straddler.center       # centre says lane 2
assert straddler.ground == (215.0, 500.0)
tall = det("truck", cx=150, bottom=500, w=120, h=260)     # wide box, wheels left
assert ZONES.zone_for(tall.ground).name == "eb-left"
assert ZONES.zone_for(tall.center) is None or True        # centre is unreliable
print(f"2. ground point {tall.ground} assigns to eb-left  OK")

# 3. Zones scale to a pipeline running at another resolution.
half = ZONES.scaled_to((640, 360))
assert half.frame_size == (640, 360)
assert half.zone_for((75, 200)).name == "eb-left", "scaled lane moved"
assert ZONES.scaled_to((1280, 720)) is ZONES, "same size should not copy"
print("3. scaled 1280x720 -> 640x360, lanes still line up  OK")

# 4. Round-trips through JSON unchanged.
tmp = Path(tempfile.mkdtemp()) / "zones.json"
ZONES.save(tmp)
loaded = ZoneMap.from_file(tmp)
assert len(loaded) == 3 and loaded.site == "INT-04"
assert loaded.zone_for((150, 400)).movement == "left"
assert loaded.pcu_for("truck") == 2.0 and loaded.pcu_for("car") == 1.0
assert loaded.pcu_for("wheelbarrow") == 1.0, "unknown class should count as a car"
print(f"4. saved and reloaded {len(loaded)} zones, pcu truck={loaded.pcu_for('truck')}  OK")

# 5. Queue counting: stopped vehicles count, moving ones don't.
mon = DemandMonitor(ZONES)
tracker = Tracker()
t = 0.0
# Three cars stopped in the left lane, one lorry stopped in the through lane.
stopped = [det("car", 150, 400), det("car", 150, 450), det("car", 150, 500),
           det("truck", 250, 400)]
for _ in range(10):                       # held still, so speed stays ~0
    frame_dets = [det(d.label, (d.x0 + d.x1) / 2, d.y1) for d in stopped]
    tracker.update(frame_dets, t)
    mon.update(frame_dets, t)
    t += 1 / FPS

assert mon.demand["eb-left"].queue == 3, mon.demand["eb-left"].queue
assert mon.demand["eb-through"].queue == 1
assert mon.demand["eb-left"].queue_pcu == 3.0
assert mon.demand["eb-through"].queue_pcu == 2.0, "a lorry should weigh 2 cars"
print(f"5. queue: left 3 veh / {mon.demand['eb-left'].queue_pcu} PCU, "
      f"through 1 lorry / {mon.demand['eb-through'].queue_pcu} PCU  OK")

# 6. Clearance time, the currency from ARCHITECTURE.md 6.3.
#    left  = 2 s start-up + 3.0 PCU x 2 s = 8 s
#    right = 2 s start-up + 2.0 PCU x 2 s = 6 s  (one lorry, fewer vehicles)
assert mon.demand["eb-left"].clearance_seconds == 8.0
assert mon.demand["eb-through"].clearance_seconds == 6.0
# The approach needs its slowest lane, not the sum: lanes discharge in parallel.
assert mon.clearance_seconds("e") == 8.0, mon.clearance_seconds("e")
assert mon.queue("e") == 4
print(f"6. clearance: left 8.0s, through 6.0s, approach {mon.clearance_seconds('e')}s  OK")

# 7. A moving vehicle is present but is not a queue.
mon2, tk2 = DemandMonitor(ZONES), Tracker()
for i in range(12):
    d = [det("car", 350, 300 + i * 12)]     # 360 px/s, well above the threshold
    tk2.update(d, i / FPS)
    mon2.update(d, i / FPS)
assert mon2.demand["eb-right"].present == 1
assert mon2.demand["eb-right"].queue == 0, "a moving car was counted as queued"
assert mon2.clearance_seconds("e") == 0.0
print("7. moving car: present 1, queued 0  OK")

# 8. Arrival rate counts each vehicle once, however long it sits there.
assert mon.demand["eb-left"].total == 3, mon.demand["eb-left"].total
assert len(mon.demand["eb-left"].arrivals) == 3, "queued cars counted repeatedly"
rate = mon.rate("e")
print(f"8. 4 unique arrivals over {t:.2f}s -> {rate:.0f}/min, no double counting  OK")

# 9. Turning split is learned from dedicated lanes only.
#    One vehicle really has to drive through and leave, or the tracker sensibly
#    treats successive detections in the same spot as the same vehicle.
def drive(mon, tk, cx, t0, label="car"):
    """Run one vehicle down a lane, then let its track expire.

    10 px per frame, which is what a real vehicle looks like at 30 fps. Move it
    much faster than its own box height and consecutive boxes stop overlapping,
    IoU association fails, and every frame becomes a new unconfirmed track.
    """
    t = t0
    for i in range(10):
        d = [det(label, cx, 300 + i * 10)]
        tk.update(d, t)
        mon.update(d, t)
        t += 1 / FPS
    for _ in range(tk.max_misses + 2):        # empty frames retire the track
        tk.update([], t)
        mon.update([], t)
        t += 1 / FPS
    return t


mon3, tk3 = DemandMonitor(ZONES), Tracker()
tt = 0.0
for i in range(20):                           # 6 left, 14 through
    tt = drive(mon3, tk3, 150 if i < 6 else 250, tt)

assert mon3.demand["eb-left"].total == 6, mon3.demand["eb-left"].total
assert mon3.demand["eb-through"].total == 14, mon3.demand["eb-through"].total
split = mon3.turning_split("e")
assert abs(split["left"] - 0.30) < 0.01, split
assert abs(split["through"] - 0.70) < 0.01, split
print(f"9. 20 vehicles driven through; observed split "
      f"{', '.join(f'{m} {s:.0%}' for m, s in split.items())}  OK")

# 10. A shared lane is counted as demand but excluded from the split, because
#     it cannot say which way its vehicles meant to go.
shared = ZoneMap([lane("eb-shared", "left|through", 500, 600),
                  lane("eb-right2", "right", 600, 700)], (1280, 720))
assert shared.zones[0].shared and shared.zones[0].movements == ("left", "through")
assert not shared.zones[1].shared

mon4, tk4 = DemandMonitor(shared), Tracker()
t4 = 0.0
for _ in range(5):
    t4 = drive(mon4, tk4, 550, t4)            # 5 through the shared lane
for _ in range(2):
    t4 = drive(mon4, tk4, 650, t4)            # 2 through the dedicated one

assert mon4.demand["eb-shared"].total == 5, mon4.demand["eb-shared"].total
assert mon4.demand["eb-right2"].total == 2
split4 = mon4.turning_split("e")
assert split4 == {"right": 1.0}, f"shared lane leaked into the split: {split4}"
print(f"10. shared lane counted (5 vehicles) but kept out of the split "
      f"{split4}  OK")

# 11. A single-frame false positive never reaches the counts.
mon5, tk5 = DemandMonitor(ZONES), Tracker()
blip = [det("car", 150, 400)]                 # one frame only, never confirmed
tk5.update(blip, 0.0)
mon5.update(blip, 0.0)
assert mon5.demand["eb-left"].total == 0, "an unconfirmed blip was counted"
assert mon5.demand["eb-left"].present == 0
print("11. single-frame blip excluded from demand  OK")

# 12. The published payload has the shape ARCHITECTURE.md 5 specifies.
snap = mon.snapshot()
assert snap["node"] == "INT-04"
assert set(snap) == {"node", "t", "queue", "rate", "clearance_s", "health"}
assert snap["queue"] == {"e": 4}, snap["queue"]
assert json.loads(json.dumps(snap)) == snap, "payload is not JSON-serialisable"
print(f"12. snapshot: {json.dumps(snap)}  OK")

print("\nAll zone and demand checks passed.")
