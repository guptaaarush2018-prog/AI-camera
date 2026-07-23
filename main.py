#!/usr/bin/env python3
"""AI camera — object detection on a Raspberry Pi 5 with a Hailo AI HAT.

Usage:
    python3 main.py                          # live preview, Escape/q or Ctrl-C to stop
    python3 main.py --headless                # no window, print detections
    python3 main.py --video clip.mp4          # run against a file instead
    python3 main.py --video clip.mp4 --save out.mp4 --headless
    python3 main.py --model path/to.hef -c 0.6
"""

import argparse
import json
import signal
import sys
import time

import cv2

from aicam.detectors.hailo_detector import (
    DEFAULT_LABELS,
    DEFAULT_MODEL,
    HailoDetector,
)
from aicam.demand import DemandMonitor
from aicam.draw import draw_detections, draw_zones
from aicam.pipeline import CameraPipeline
from aicam.tracking import Tracker
from aicam.video import VideoPipeline
from aicam.zones import ZoneMap

WINDOW_NAME = "AI Camera"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL, help="path to a .hef network")
    parser.add_argument("--labels", default=DEFAULT_LABELS, help="path to a labels file")
    parser.add_argument("-c", "--confidence", type=float, default=0.5,
                        help="minimum detection score (0-1)")
    parser.add_argument("--width", type=int, help="display width (default: 1280, or the video's own)")
    parser.add_argument("--height", type=int, help="display height (default: 720, or the video's own)")
    parser.add_argument("--headless", action="store_true",
                        help="no preview window; log detections to stdout")
    parser.add_argument("--no-track", action="store_true",
                        help="detect only; no IDs, speed or unique counts")
    parser.add_argument("--zones", help="lane zone config, e.g. config/int-04.json")

    source = parser.add_argument_group("video file input")
    source.add_argument("--video", help="read from a video file instead of the camera")
    source.add_argument("--realtime", action="store_true",
                        help="play a video at its own frame rate rather than as fast as possible")
    source.add_argument("--loop", action="store_true", help="restart the video when it ends")
    source.add_argument("--save", help="write an annotated video to this path")
    source.add_argument("--max-frames", type=int, help="stop after this many frames")
    return parser.parse_args()


def open_writer(path: str, size: tuple[int, int], fps: float):
    """A VideoWriter for `path`, picking a codec the container will accept."""
    fourcc = cv2.VideoWriter_fourcc(*("MJPG" if path.lower().endswith(".avi") else "mp4v"))
    writer = cv2.VideoWriter(path, fourcc, fps, size)
    if not writer.isOpened():
        raise RuntimeError(
            f"Could not open {path} for writing. Try an .avi extension, which "
            "uses MJPG and is available in every OpenCV build."
        )
    return writer


def build_pipeline(args, detector, processors):
    """Camera or video file, depending on --video."""
    explicit_size = (args.width, args.height) if args.width and args.height else None

    if args.video:
        pipeline = VideoPipeline(
            args.video, detector,
            display_size=explicit_size,
            processors=processors,
            realtime=args.realtime,
            loop=args.loop,
        )
        where = (f"{args.video}: {pipeline.native_size[0]}x{pipeline.native_size[1]} "
                 f"@ {pipeline.fps:.1f} fps")
        if pipeline.duration:
            where += f", {pipeline.duration:.0f}s"
        print(where, file=sys.stderr)
        return pipeline, pipeline.fps

    return CameraPipeline(
        detector,
        display_size=explicit_size or (1280, 720),
        processors=processors,
    ), 30.0


def main():
    args = parse_args()

    detector = HailoDetector(
        model_path=args.model,
        labels_path=args.labels,
        threshold=args.confidence,
    )

    tracker = None if args.no_track else Tracker()
    processors = [] if tracker is None else [tracker]

    pipeline, fps = build_pipeline(args, detector, processors)

    monitor = None
    if args.zones:
        # Zones are drawn against one resolution and may be used at another.
        zone_map = ZoneMap.from_file(args.zones).scaled_to(pipeline.display_size)
        monitor = DemandMonitor(zone_map)
        # Appended, so it runs after the tracker — it needs IDs to tell an
        # arrival from a vehicle it already counted, and speed to spot a queue.
        pipeline.processors.append(monitor)
        print(f"{len(zone_map)} zones from {args.zones}, approaches: "
              f"{', '.join(zone_map.approaches)}", file=sys.stderr)
        if tracker is None:
            print("--no-track with --zones: queue lengths yes, arrival rates no.",
                  file=sys.stderr)

    # Annotating a saved video needs the display image even with no window.
    want_display = not args.headless or bool(args.save)
    writer = open_writer(args.save, pipeline.display_size, fps) if args.save else None

    running = True

    def handle_sigint(_signum, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, handle_sigint)

    with pipeline:
        pipeline.start()

        last_report = time.monotonic()
        frames_since_report = 0
        total = 0

        for frame in pipeline.frames(want_display=want_display):
            if not running:
                break

            if want_display:
                if monitor is not None:
                    draw_zones(frame.display, monitor.zones)
                draw_detections(frame.display, frame.detections)
                if writer is not None:
                    writer.write(frame.display)

            if args.headless:
                for det in frame.detections:
                    track_id = det.extra.get("track_id", "-")
                    print(f"[{frame.index}] #{track_id} {det.label} {det.score:.2f} "
                          f"({det.x0},{det.y0})-({det.x1},{det.y1})")
            else:
                cv2.imshow(WINDOW_NAME, frame.display)
                key = cv2.waitKey(1) & 0xFF
                if key == 27 or key == ord("q"):  # Escape or q
                    running = False

            total += 1
            if args.max_frames and total >= args.max_frames:
                break

            frames_since_report += 1
            now = time.monotonic()
            if now - last_report >= 5:
                rate = frames_since_report / (now - last_report)
                report = f"{rate:.1f} FPS, {len(frame.detections)} objects"
                if tracker is not None:
                    # Unique objects since startup, not a per-frame headcount.
                    totals = ", ".join(
                        f"{n} {label}" for label, n in sorted(tracker.counts.items())
                    )
                    report += f" | {len(tracker.confirmed_tracks)} tracked"
                    if totals:
                        report += f" | seen: {totals}"
                print(report, file=sys.stderr)
                if monitor is not None:
                    print(json.dumps(monitor.snapshot()), file=sys.stderr)
                last_report = now
                frames_since_report = 0

    if writer is not None:
        writer.release()
        print(f"Wrote {total} frames to {args.save}")
    if not args.headless:
        cv2.destroyAllWindows()
    if tracker is not None and tracker.counts:
        print("Unique objects: " + ", ".join(
            f"{n} {label}" for label, n in sorted(tracker.counts.items())))

    if monitor is not None:
        print("Final state: " + json.dumps(monitor.snapshot()))
        for approach in monitor.zones.approaches:
            split = monitor.turning_split(approach)
            if split:
                # Learned from what vehicles were observed to do, not assumed.
                shares = ", ".join(f"{m} {s:.0%}" for m, s in split.items())
                print(f"Turning split, approach {approach}: {shares}")
    print("Stopped.")


if __name__ == "__main__":
    main()
