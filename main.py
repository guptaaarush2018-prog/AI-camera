#!/usr/bin/env python3
"""AI camera — live object detection on a Raspberry Pi 5 with a Hailo AI HAT.

Usage:
    python3 main.py                          # preview with boxes, Ctrl-C to stop
    python3 main.py --headless                # no window, print detections
    python3 main.py --model path/to.hef -c 0.6
"""

import argparse
import signal
import sys
import time

from picamera2 import Preview

from aicam.detectors.hailo_detector import (
    DEFAULT_LABELS,
    DEFAULT_MODEL,
    HailoDetector,
)
from aicam.draw import make_overlay
from aicam.pipeline import CameraPipeline


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
    return parser.parse_args()


def main():
    args = parse_args()

    detector = HailoDetector(
        model_path=args.model,
        labels_path=args.labels,
        threshold=args.confidence,
    )
    display_size = (args.width, args.height)

    running = True

    def handle_sigint(_signum, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, handle_sigint)

    with CameraPipeline(detector, display_size=display_size) as pipeline:
        if not args.headless:
            # Swap QTGL for Preview.DRM on a console-only Pi.
            pipeline.picam2.start_preview(Preview.QTGL, x=0, y=0,
                                          width=args.width, height=args.height)

        last_report = time.monotonic()
        frames_since_report = 0

        for frame in pipeline.frames():
            if not running:
                break

            if args.headless:
                for det in frame.detections:
                    print(f"[{frame.index}] {det.label} {det.score:.2f} "
                          f"({det.x0},{det.y0})-({det.x1},{det.y1})")
            else:
                pipeline.picam2.set_overlay(make_overlay(frame.detections, display_size))

            frames_since_report += 1
            now = time.monotonic()
            if now - last_report >= 5:
                fps = frames_since_report / (now - last_report)
                print(f"{fps:.1f} FPS, {len(frame.detections)} objects", file=sys.stderr)
                last_report = now
                frames_since_report = 0

    print("Stopped.")


if __name__ == "__main__":
    main()
