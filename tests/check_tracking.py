"""Offline sanity check for aicam.tracking — no camera, no Hailo."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aicam.detection import Detection
from aicam.tracking import Tracker

FPS = 30.0


def det(label, cx, cy, w=60, h=40, score=0.9):
    return Detection(label, score, int(cx - w / 2), int(cy - h / 2),
                     int(cx + w / 2), int(cy + h / 2))


def run(frames, **kw):
    t = Tracker(**kw)
    for i, dets in enumerate(frames):
        t.update(dets, timestamp=i / FPS)
    return t


# 1. A car moving right at 300 px/s (10 px/frame) keeps one ID.
frames = [[det("car", 100 + 10 * i, 300)] for i in range(30)]
tk = run(frames)
last = frames[-1][0]
assert len(tk.tracks) == 1, tk.tracks
assert tk.counts == {"car": 1}, tk.counts
assert last.extra["track_id"] == 1
speed = last.extra["speed"]
assert 280 < speed < 320, f"speed {speed}, expected ~300"
assert last.extra["heading"] == "E", last.extra
print(f"1. single moving car: id=1, speed={speed:.0f}px/s, heading=E  OK")

# 2. A stationary car reports no heading and ~0 speed.
tk = run([[det("car", 400, 300)] for _ in range(20)])
d = det("car", 400, 300)
tk.update([d], timestamp=20 / FPS)
assert d.extra["speed"] < 1.0, d.extra
assert "heading" not in d.extra, d.extra
print(f"2. stationary car: speed={d.extra['speed']:.2f}px/s, no heading  OK")

# 3. Two objects crossing keep distinct IDs; a person is never matched to a car.
frames = []
for i in range(30):
    frames.append([det("car", 100 + 10 * i, 300), det("person", 700 - 10 * i, 300)])
tk = run(frames)
ids = {d.extra["track_id"] for d in frames[-1]}
assert len(ids) == 2, ids
assert tk.counts == {"car": 1, "person": 1}, tk.counts
print(f"3. car + person crossing: ids={sorted(ids)}, counts={tk.counts}  OK")

# 4. A track survives a short occlusion without a new ID being issued.
tk = Tracker(max_misses=15)
for i in range(10):
    tk.update([det("car", 100 + 10 * i, 300)], timestamp=i / FPS)
for i in range(10, 20):                       # 10 frames hidden
    tk.update([], timestamp=i / FPS)
d = det("car", 100 + 10 * 20, 300)
tk.update([d], timestamp=20 / FPS)
assert d.extra["track_id"] == 1, d.extra
assert tk.counts == {"car": 1}, tk.counts
print(f"4. re-appears after 10 hidden frames: still id=1, counts={tk.counts}  OK")

# 5. A track dropped for longer than max_misses is retired, not resurrected.
tk = Tracker(max_misses=15)
for i in range(10):
    tk.update([det("car", 200, 300)], timestamp=i / FPS)
for i in range(10, 40):
    tk.update([], timestamp=i / FPS)
assert tk.tracks == [], tk.tracks
d = det("car", 200, 300)
tk.update([d], timestamp=40 / FPS)
assert d.extra["track_id"] == 2, d.extra
print("5. gone longer than max_misses: retired, new object gets id=2  OK")

# 6. A one-frame false positive never reaches the counts.
tk = Tracker(min_hits=3)
tk.update([det("truck", 500, 200)], timestamp=0)
for i in range(1, 30):
    tk.update([], timestamp=i / FPS)
assert tk.counts == {}, tk.counts
print("6. single-frame blip: excluded from counts  OK")

# 7. Headings in all four directions.
for name, (dx, dy) in {"N": (0, -10), "S": (0, 10), "E": (10, 0), "W": (-10, 0)}.items():
    frames = [[det("car", 400 + dx * i, 300 + dy * i)] for i in range(20)]
    run(frames)
    got = frames[-1][0].extra.get("heading")
    assert got == name, f"expected {name}, got {got}"
print("7. headings N/S/E/W all correct  OK")

print("\nAll tracker checks passed.")
