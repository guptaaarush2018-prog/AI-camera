#!/usr/bin/env python3
"""Basic Picamera2 driver for the Raspberry Pi camera.

Usage:
    python3 main.py preview            # live preview window for 10s
    python3 main.py preview -t 0       # preview until Ctrl-C
    python3 main.py photo out.jpg      # capture a still
    python3 main.py video out.mp4 -t 5 # record 5 seconds of H.264
"""

import argparse
import time

from picamera2 import Picamera2, Preview
from picamera2.encoders import H264Encoder
from picamera2.outputs import FfmpegOutput


def preview(args):
    picam2 = Picamera2()
    config = picam2.create_preview_configuration(main={"size": (1280, 720)})
    picam2.configure(config)
    # QTGL needs a desktop session; use Preview.DRM on a console-only Pi.
    picam2.start_preview(Preview.QTGL)
    picam2.start()
    try:
        if args.timeout == 0:
            print("Previewing, press Ctrl-C to stop...")
            while True:
                time.sleep(1)
        else:
            time.sleep(args.timeout)
    except KeyboardInterrupt:
        pass
    finally:
        picam2.stop()
        picam2.stop_preview()
        picam2.close()


def photo(args):
    picam2 = Picamera2()
    config = picam2.create_still_configuration()
    picam2.configure(config)
    picam2.start()
    # Give AE/AWB a moment to settle before the shot.
    time.sleep(2)
    picam2.capture_file(args.output)
    picam2.close()
    print(f"Saved {args.output}")


def video(args):
    picam2 = Picamera2()
    config = picam2.create_video_configuration(main={"size": (1280, 720)})
    picam2.configure(config)

    encoder = H264Encoder(bitrate=10_000_000)
    output = FfmpegOutput(args.output)

    picam2.start_recording(encoder, output)
    print(f"Recording {args.timeout}s to {args.output}...")
    try:
        time.sleep(args.timeout)
    except KeyboardInterrupt:
        pass
    finally:
        picam2.stop_recording()
        picam2.close()
    print(f"Saved {args.output}")


def main():
    parser = argparse.ArgumentParser(description="Raspberry Pi camera control")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("preview", help="show a live preview")
    p.add_argument("-t", "--timeout", type=int, default=10,
                   help="seconds to preview, 0 for indefinite")
    p.set_defaults(func=preview)

    p = sub.add_parser("photo", help="capture a still image")
    p.add_argument("output", nargs="?", default="image.jpg")
    p.set_defaults(func=photo)

    p = sub.add_parser("video", help="record a video")
    p.add_argument("output", nargs="?", default="video.mp4")
    p.add_argument("-t", "--timeout", type=int, default=5,
                   help="seconds to record")
    p.set_defaults(func=video)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
