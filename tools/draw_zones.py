#!/usr/bin/env python3
"""Draw lane zones on a still frame and write a site config.

This is the commissioning step from ARCHITECTURE.md 4.3 — done once per camera,
against real footage from where the camera will actually sit.

    python3 tools/draw_zones.py --video clip.mp4 --out config/int-04.json
    python3 tools/draw_zones.py --image frame.png --out config/int-04.json --site INT-04

Click to place polygon corners. Then:
    ENTER   finish this zone and name it (in the terminal)
    u       undo the last point
    r       restart this zone
    s       save and quit
    q       quit without saving

Needs a display. On a headless Pi, grab a frame with --video and run this on a
machine with a monitor — the config is just JSON and travels fine.
"""

import argparse
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aicam.zones import DEFAULT_PCU, Zone, ZoneMap  # noqa: E402

WINDOW = "Draw lane zones"
COLORS = [(0, 200, 255), (0, 255, 120), (255, 140, 0), (255, 80, 200), (120, 200, 255)]


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--video", help="take the first frame of this video")
    src.add_argument("--image", help="use this still image")
    p.add_argument("--out", required=True, help="where to write the config")
    p.add_argument("--site", default="", help="node name, e.g. INT-04")
    p.add_argument("--frame", type=int, default=0, help="which video frame to grab")
    return p.parse_args()


def load_frame(args):
    if args.image:
        image = cv2.imread(args.image)
        if image is None:
            raise SystemExit(f"Could not read {args.image}")
        return image

    capture = cv2.VideoCapture(args.video)
    if not capture.isOpened():
        raise SystemExit(f"Could not open {args.video}")
    if args.frame:
        capture.set(cv2.CAP_PROP_POS_FRAMES, args.frame)
    ok, image = capture.read()
    capture.release()
    if not ok:
        raise SystemExit(f"Could not read frame {args.frame} of {args.video}")
    return image


def render(base, zones, current):
    canvas = base.copy()
    for i, zone in enumerate(zones):
        color = COLORS[i % len(COLORS)]
        pts = [(int(x), int(y)) for x, y in zone.polygon]
        cv2.polylines(canvas, [_np_array(pts)], True, color, 2)
        cx = sum(p[0] for p in pts) // len(pts)
        cy = sum(p[1] for p in pts) // len(pts)
        cv2.putText(canvas, f"{zone.name} [{zone.movement}]", (cx - 60, cy),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)

    color = COLORS[len(zones) % len(COLORS)]
    for point in current:
        cv2.circle(canvas, point, 4, color, -1)
    if len(current) > 1:
        cv2.polylines(canvas, [_np_array(current)], False, color, 2)

    cv2.putText(canvas, f"{len(zones)} zone(s) - ENTER finish, u undo, r restart, s save, q quit",
                (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    return canvas


def _np_array(points):
    import numpy as np
    return np.array(points, dtype=np.int32)


def main():
    args = parse_args()
    base = load_frame(args)
    height, width = base.shape[:2]
    print(f"Frame is {width}x{height}")

    zones: list[Zone] = []
    current: list[tuple[int, int]] = []

    def on_mouse(event, x, y, _flags, _param):
        if event == cv2.EVENT_LBUTTONDOWN:
            current.append((x, y))

    cv2.namedWindow(WINDOW)
    cv2.setMouseCallback(WINDOW, on_mouse)

    while True:
        cv2.imshow(WINDOW, render(base, zones, current))
        key = cv2.waitKey(20) & 0xFF

        if key in (13, 10):                      # ENTER
            if len(current) < 3:
                print("A zone needs at least 3 points.")
                continue
            name = input("Zone name (e.g. eb-left): ").strip() or f"zone-{len(zones) + 1}"
            approach = input("Approach [n/e/s/w]: ").strip().lower() or "n"
            movement = input("Movement [left/through/right, or left|through]: ").strip() or "through"
            zones.append(Zone(name, approach, movement, tuple(map(tuple, current))))
            current = []
            print(f"Added {name}. {len(zones)} zone(s) so far.")
        elif key == ord("u") and current:
            current.pop()
        elif key == ord("r"):
            current = []
        elif key == ord("s"):
            break
        elif key == ord("q"):
            print("Quit without saving.")
            cv2.destroyAllWindows()
            return

    cv2.destroyAllWindows()

    if not zones:
        print("No zones drawn, nothing written.")
        return

    zone_map = ZoneMap(zones, (width, height), dict(DEFAULT_PCU), args.site)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    zone_map.save(args.out)
    print(f"Wrote {len(zones)} zone(s) to {args.out}")


if __name__ == "__main__":
    main()
