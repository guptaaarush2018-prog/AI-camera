#!/usr/bin/env python3
"""AI camera — live object detection on a Raspberry Pi 5 with a Hailo AI HAT.

Usage:
    python3 main.py                          # preview with boxes, Escape/q or Ctrl-C to stop
    python3 main.py --headless                # no window, print detections
    python3 main.py --model path/to.hef -c 0.6
"""

import argparse
import signal
import sys
import time

import cv2

from aicam.detectors.hailo_detector import (
    DEFAULT_LABELS,
    DEFAULT_MODEL,
    HailoDetector,
)
from aicam.draw import draw_detections
from aicam.pipeline import CameraPipeline
from aicam.tracking import Tracker

WINDOW_NAME = "AI Camera"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL, help="path to a .hef network")
    parser.add_argument("--labels", default=DEFAULT_LABELS, help="path to a labels file")
    parser.add_argument("-c", "--confidence", type=float, default=0.5,
                        help="minimum detection score (0-1)")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--headless", action="store_true",
                        help="no preview window; log detections to stdout")
    parser.add_argument("--no-track", action="store_true",
                        help="detect only; no IDs, speed or unique counts")
    return parser.parse_args()


def main():
    args = parse_args()

    detector = HailoDetector(
        model_path=args.model,
        labels_path=args.labels,
        threshold=args.confidence,
    )
    display_size = (args.width, args.height)

    tracker = None if args.no_track else Tracker()
    processors = [] if tracker is None else [tracker]

    running = True

    def handle_sigint(_signum, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, handle_sigint)

    with CameraPipeline(
        detector, display_size=display_size, processors=processors
    ) as pipeline:
        pipeline.start()

        last_report = time.monotonic()
        frames_since_report = 0

        for frame in pipeline.frames(want_display=not args.headless):
            if not running:
                break

            if args.headless:
                for det in frame.detections:
                    track_id = det.extra.get("track_id", "-")
                    print(f"[{frame.index}] #{track_id} {det.label} {det.score:.2f} "
                          f"({det.x0},{det.y0})-({det.x1},{det.y1})")
            else:
                draw_detections(frame.display, frame.detections)
                cv2.imshow(WINDOW_NAME, frame.display)
                key = cv2.waitKey(1) & 0xFF
                if key == 27 or key == ord("q"):  # Escape or q
                    running = False

            frames_since_report += 1
            now = time.monotonic()
            if now - last_report >= 5:
                fps = frames_since_report / (now - last_report)
                report = f"{fps:.1f} FPS, {len(frame.detections)} objects"
                if tracker is not None:
                    # Unique objects since startup, not a per-frame headcount.
                    totals = ", ".join(
                        f"{n} {label}" for label, n in sorted(tracker.counts.items())
                    )
                    report += f" | {len(tracker.confirmed_tracks)} tracked"
                    if totals:
                        report += f" | seen: {totals}"
                print(report, file=sys.stderr)
                last_report = now
                frames_since_report = 0

    if not args.headless:
        cv2.destroyAllWindows()
    print("Stopped.")


if __name__ == "__main__":
    main()
