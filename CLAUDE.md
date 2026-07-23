# AI Camera — adaptive traffic signal sensing

Vision-based traffic sensing on a Raspberry Pi 5 + Hailo-8L NPU. A camera on a pole
counts and tracks traffic, works out what each approach needs, and tells neighbouring
intersections what is heading their way.

Read [ARCHITECTURE.md](ARCHITECTURE.md) first — it is the design document and the source
of truth for intent. This file covers how to work in the repo.

## Current state

| | |
|---|---|
| Detection | Built — Hailo-8L, stock YOLOv8s `.hef`, ~30 fps at 1280×720 |
| Tracking | Built — IDs, speed, heading, unique counts ([aicam/tracking.py](aicam/tracking.py)) |
| Video file input | Built — [aicam/video.py](aicam/video.py), makes detection repeatable |
| Lane zones | Built — [aicam/zones.py](aicam/zones.py) + [tools/draw_zones.py](tools/draw_zones.py) |
| Queue / arrival rate / turning split | Built — [aicam/demand.py](aicam/demand.py), **in pixel units** |
| Homography (real units) | **Not built** — the next real gap |
| MQTT / coordination (Phase 2) | Not built |
| Signal advisory (Phase 3) | Not built |

Phase 1 is functionally complete but **validated only against synthetic input** — the
tests prove the arithmetic, not the perception. Nothing has been checked against real
traffic footage. Keep `ARCHITECTURE.md` in sync when a piece actually lands.

## Running it

```bash
.venv/bin/python main.py                 # preview window with boxes
.venv/bin/python -u main.py --headless   # no window, detections to stdout
.venv/bin/python main.py --no-track      # detection only, no IDs or counts

# From a file instead of the camera — repeatable, and the basis of the demand study
.venv/bin/python main.py --video clip.mp4 --realtime
.venv/bin/python -u main.py --video clip.mp4 --headless --save out.avi

# With lane zones: per-lane queues, arrival rates and turning splits
python3 tools/draw_zones.py --video clip.mp4 --out config/int-04.json --site INT-04
.venv/bin/python main.py --video clip.mp4 --zones config/int-04.json
```

Prefer `.avi` for `--save`: it uses MJPG, which every OpenCV build has. `.mp4`
needs an mp4v encoder that may not be present.

Always use `.venv/bin/python` — the venv is built with `--system-site-packages` because
`picamera2`, `libcamera` and the Hailo bindings are apt-installed system packages, not
pip ones. `uv run` and a bare `python3` will not find them.

Use `-u` when piping output anywhere. Without it a killed run flushes nothing and looks
like a hang.

## Tests

```bash
python3 tests/check_tracking.py          # tracker, pure synthetic detections
.venv/bin/python tests/check_video.py    # video pipeline (needs cv2, not the Hailo)
.venv/bin/python tests/check_zones.py    # lane zones and demand measurement
```

Plain asserts, no pytest (not installed), no camera or Hailo needed — they drive the
code with synthetic detections and a generated video file. Anything that can be tested
off-hardware should be, because hardware runs are slow to iterate and impossible to
make deterministic. That is the main reason `VideoPipeline` exists.

## Layout

```
main.py                      CLI: wires detector + pipeline + processors together
aicam/detection.py           Detection and Frame — the types everything else speaks
aicam/pipeline.py            FramePipeline base + CameraPipeline (Picamera2)
aicam/video.py               VideoPipeline — same Frames, read from a file
aicam/detectors/base.py      Detector interface — swap Hailo for anything else here
aicam/detectors/hailo_*.py   Hailo-8L via Picamera2's HailoRT wrapper
aicam/tracking.py            Tracker: detections -> persistent objects
aicam/zones.py               Lane zones: pixels -> approach + movement
aicam/demand.py              DemandMonitor: queue, arrival rate, turning split
aicam/draw.py                Preview overlay
config/*.json                Per-site zone configs (not code — re-striping is an edit)
tools/draw_zones.py          Commissioning: click zones onto a still, write a config
site/index.html              Pitch site (published as an Artifact)
```

## How to extend it

**Add a processor.** Anything that runs per frame — lane zones, queue measurement,
MQTT publishing — is a `Processor`: a callable taking a `Frame`, annotating it in
place. Register it in `main.py` via `CameraPipeline(processors=[...])`. This is the
intended extension point; resist adding stages to the pipeline itself.

**Pass data forward via `Detection.extra`.** A dict, deliberately schema-free, so a new
stage does not force a change to the core types. `draw.py` picks up known keys
automatically.

**Two streams, on purpose.** The camera runs a display-res `main` stream and a
model-res `lores` stream so nothing is downscaled in Python. Detections are scaled to
the *display* size, so all downstream pixel coordinates share one frame of reference.

## Conventions

- Comments explain *why*, not what. Existing modules set the density — match it.
- Docstrings on anything non-obvious, especially where a constant encodes a real-world
  fact (saturation headway, PCU weights, clearance intervals). Say where the number
  came from.
- Traffic-engineering constants belong in config, not literals. Different countries and
  junction geometries use different values, and an engineer will want to overrule ours.
- Type hints throughout. Dataclasses for data.
- No new dependencies without a strong reason — this runs on a Pi, from apt packages.

## Gotchas

- **`Detection` is unhashable.** It is a mutable dataclass, so `__hash__` is `None`.
  Never use one as a dict key or put it in a set; key by `id()` or use lists of pairs.
- **Predicted state must not feed estimates.** `Track.coast()` moves a box along its
  last known velocity during occlusion but deliberately does not append to history —
  otherwise speed estimates would confirm their own guesses. Preserve that separation.
- **Frame timestamps are source time, not wall-clock.** The camera uses
  `time.monotonic()`; video uses `index / fps`. The tracker divides by the gap between
  them, so using the clock on a file would make every speed depend on decode rate.
- **Both sources hand the model BGR.** OpenCV decodes to BGR, and Picamera2's
  `RGB888` lores stream is documented as blue, green, red in memory. They agree, but
  neither is necessarily what the model wants — worth measuring whether swapping
  channels raises confidence scores.
- **Pixels are not metres.** Speed is px/s and means nothing across camera mountings.
  Real units need a one-time homography, which does not exist yet. Do not report px/s
  to anyone outside the codebase as though it were a speed.
- **Use the ground-contact point for anything spatial.** `Detection.ground` (bottom-centre)
  is where the vehicle touches the road; `Detection.center` floats around its windscreen
  and drifts across lane boundaries at an angle. Tracking and zone assignment both use
  `ground` — keep it that way.
- **Processor order matters.** `DemandMonitor` must run *after* `Tracker`: it needs
  track IDs to tell a new arrival from one it has already counted, and speed to tell a
  queue from moving traffic. `main.py` appends it for exactly this reason.
- **Honour `confirmed`.** The tracker sets `extra["confirmed"]` once a track passes
  `min_hits`. Any stage that counts things must check it, or a one-frame false positive
  becomes a vehicle in the totals.
- **Objects moving faster than their own box height break association.** IoU matching
  needs consecutive boxes to overlap. Real traffic at 30 fps moves a few pixels per
  frame, so this only bites in synthetic tests — write them with realistic motion.
- **Pi 5 has two CSI ports.** A four-approach junction needs two Pis, or IP cameras.
- **The Hailo does not need 30 fps.** 10 fps is ample for traffic and leaves headroom
  for more streams per accelerator.
- `hailort*.log` is gitignored — HailoRT writes megabytes of it into the working
  directory.

## The constraint that outranks everything

The vision system never drives signal hardware. It emits *recommendations* to a
separate, deliberately simple safety layer that enforces conflict matrix, minimum
green, clearance intervals and pedestrian guarantees, and that may reject anything.
Every failure path ends at an ordinary fixed-time traffic light.

If a change would move decision-making authority toward the model, or make the safety
logic more complicated, it is the wrong change. The intelligent part is allowed to be
wrong; the safety part is not allowed to be complicated.
