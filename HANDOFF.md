# Handoff → Pi instance (presentation-day runbook)

You are the Claude Code instance on the Raspberry Pi. This note is from the
instance running on the Mac the night before. Read it once, top to bottom, then
execute. Everything here is context the repo alone won't give you.

## Situation

- **Tomorrow (Friday) is presentation/competition day.** The team presents *with*
  this Pi physically present.
- **Working window: ~9:00–12:00 (3 hours)**, plus buffer "if needed."
- **The deck is basically done.** Do not build slides. Your job is the live demo
  + de-risking + practice.
- Project = vision-based adaptive traffic sensing (see `ARCHITECTURE.md`, `CLAUDE.md`).
  Phase 1 (detect → track → zones → demand) is built but **validated only on
  synthetic input** — nothing has been run against real traffic footage yet.
  **Tomorrow is the first time this system meets real traffic. That is the whole
  point of the session.**

## The one rule that outranks the rest

**Record the demo working early, so what you show on stage is never the thing that
might crash on stage.** Capture a clean screen recording of detection running in
Block B and again in Block C. Live is nicer; recorded is insurance. Have both.

## What the Mac instance changed this session (FYI — may be uncommitted)

1. **`index.html` (website sim)** — rewrote the vehicle motion from a snap-to-slot
   model to a car-following model (smooth acceleration + braking). Fixes "cars
   jump on green" and "cars freeze at green." **Metrics/verdict unchanged**
   (adaptive still wins ~−57% mean wait). Verified in a real browser. **Do not
   touch the sim tomorrow** — it's frozen on purpose.
2. **`CLAUDE.md`** — added an "Upgrading the detector model" section; fixed a stale
   `site/index.html` → `index.html` path.
3. **`aicam/detectors/hailo_detector.py`** — added a comment near `DEFAULT_MODEL`
   about the yolov8m upgrade path. **No behavioural change; default is still
   yolov8s.**

If you `git pull` and see these, good. If not, they live on the Mac — they don't
block any of your tasks below.

## Decisions already made — do NOT relitigate under time pressure

- **Demo on stock `yolov8s_h8l.hef`.** The yolov8m upgrade is researched and
  documented but is a *post-competition* change. Demo day is not the day to swap
  models. Keep the default.
- **Sim is frozen.** No code changes to `index.html`.
- **Honesty is the pitch.** Never claim the sim's −57% as a measured result from
  this system. The honest framing (below) is a feature, not a weakness.

## Runbook (time-boxed, each block has a fallback)

| Block | Time | Goal | Fallback |
|---|---|---|---|
| **A — Smoke test** | 9:00–9:30 | `.venv/bin/python main.py` → preview window, boxes, fps. Confirm camera + Hailo + venv all live after the Pi sat idle. | If broken, you have runway to fix now. Check: PCIe Gen3 enabled, `hailo-all` installed, `.venv` intact, model at `/usr/share/hailo-models/yolov8s_h8l.hef`. |
| **B — Capture the money shot** | 9:30–10:00 | Point camera at real traffic (window/road) OR `--video clip.mp4`. Screen-record boxes + live counts. Save an annotated `.avi` too (`--save out.avi`, MJPG). | If no real traffic is visible from the venue, download a traffic clip onto the Pi and use `--video`. Get a clip staged before you need it. |
| **C — Zones on real footage** | 10:00–10:30 | Grab a still *from the real camera angle*, run `tools/draw_zones.py`, draw the lanes, then `main.py --zones …`. Record the per-lane queues + PCU clearance + turning split. | This is the "lanes are software" proof — highest-value visual if it lands. |
| **D — Freeze the demo** | 10:30–11:00 | Pick live vs recorded, script the exact on-stage sequence, test the website sim in the presentation browser. | After this block: change nothing. |
| **E — Practice** | 11:00–12:00 | Full run-throughs, real timing, Q&A drill. | Buffer is your "if needed." |

Commands (from `CLAUDE.md`; always `.venv/bin/python`, `-u` when piping):
```bash
.venv/bin/python main.py                              # preview, boxes
.venv/bin/python -u main.py --headless                # detections to stdout
.venv/bin/python main.py --video clip.mp4 --realtime  # from a file
.venv/bin/python -u main.py --video clip.mp4 --headless --save out.avi
python3 tools/draw_zones.py --video clip.mp4 --out config/int-04.json --site INT-04
.venv/bin/python main.py --video clip.mp4 --zones config/int-04.json
```

## Please verify and write down the answers (only the hardware can tell us)

These close real gaps in the pitch — capture the answers for the team:
1. **Does detection run, and at what fps** on the current setup? (We cite "~30 fps"
   — confirm it.)
2. **On real footage, which classes detect reliably** — car, truck, bus,
   motorcycle, bicycle, person? This is the first real test of the perception claim.
3. **Do the zone polygons line up** with the actual lanes in the camera's view?
4. **Is there usable real traffic** at the venue, or is a downloaded video the plan?
5. **Any environment breakage** after idle time (venv / `hailo-all` / PCIe Gen3)?

## Q&A answers the presenters should have cold

1. **"What's *your* efficiency number?"** → "Deployed systems (Surtrac, etc.) show
   ~40%. Our simulation on identical demand shows ~57%, consistent with that. What
   we built and validated is the perception layer — detection, tracking, per-lane
   demand. The control policy is simulated, and we're precise about that."
2. **"Isn't AI running traffic lights dangerous?"** → AI is an optimizer, not an
   authority: it picks from pre-approved phases; conflict matrix + min-green +
   clearance + pedestrian guarantee are enforced *below* it; crash → fixed-time
   fallback. (Strongest answer — lean in.)
3. **"Lanes / spillback?"** → One camera per approach; lanes drawn in software as
   zones; each vehicle assigned by its ground-contact point. Queue-length-in-metres
   is a hard override in the full design (spillback interrupt). The web sim is a
   simplified single-junction illustration, so it shows the core policy, not that
   interrupt.

## The demand math (for on-screen explanation if asked)

`green_needed = 2s startup + (Σ PCU of stopped vehicles × 2s headway)`.
PCU: bicycle 0.2, motorcycle 0.4, car 1.0, bus 2.0, truck 2.0 (unknown → 1.0).
Startup is paid once per queue, not per vehicle. Only *stopped* vehicles count.
Per approach it's the *longest lane*, not the sum. Clearance sets green *duration*;
accumulated waiting time decides *who* goes first; min/max green clamp it in the
safety layer.

— Mac instance, signing off. Good luck. Record early.
