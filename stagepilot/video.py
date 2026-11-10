"""Offline, experimental HOG person detection on a local recording."""
import argparse
import json
import time
from pathlib import Path

import cv2

def main():
    parser = argparse.ArgumentParser(description="Offline StagePilot person-detection preview (no camera control)")
    parser.add_argument("video", type=Path, help="Local video file")
    parser.add_argument("--start", type=float, default=0, help="Start time in seconds")
    parser.add_argument("--duration", type=float, default=30, help="Seconds of video to process")
    parser.add_argument("--fps", type=float, default=2, help="Sampled frames per second")
    parser.add_argument("--output", type=Path, default=Path("stagepilot-preview.mp4"), help="Preview video path")
    args = parser.parse_args()
    if args.start < 0 or args.duration <= 0 or not 0 < args.fps <= 30:
        parser.error("start must be nonnegative, duration positive, and fps between 0 and 30")
    if not args.video.is_file():
        parser.error("video must be an existing local file")
    if args.video.resolve() == args.output.resolve():
        parser.error("output must differ from input")
    if args.output.exists():
        parser.error("output already exists; choose another filename")

    if not hasattr(cv2, "HOGDescriptor"):
        raise SystemExit("This baseline needs OpenCV 4.10; install opencv-python==4.10.0.84 in .venv")
    capture = cv2.VideoCapture(str(args.video))
    if not capture.isOpened():
        raise SystemExit("Could not open video")
    hog = cv2.HOGDescriptor()
    hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
    writer = None
    total = frames_with_boxes = 0
    start_clock = time.monotonic()
    try:
        while total / args.fps < args.duration:
            timestamp = args.start + total / args.fps
            capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
            ok, frame = capture.read()
            if not ok:
                break
            height, width = frame.shape[:2]
            scale = min(1.0, 960 / width)
            frame = cv2.resize(frame, (int(width * scale), int(height * scale)))
            h, w = frame.shape[:2]
            boxes, weights = hog.detectMultiScale(frame, winStride=(8, 8), padding=(8, 8), scale=1.05)
            for x, y, bw, bh in boxes:
                cv2.rectangle(frame, (x, y), (x + bw, y + bh), (0, 200, 255), 2)
            if len(boxes):
                frames_with_boxes += 1
            lines = [f"SIMULATION ONLY | t={timestamp:.1f}s | boxes={len(boxes)}",
                     "UNVERIFIED DETECTIONS | motion disabled"]
            for i, line in enumerate(lines):
                cv2.putText(frame, line, (12, 26 + i * 26), cv2.FONT_HERSHEY_SIMPLEX, .55, (0, 0, 0), 4)
                cv2.putText(frame, line, (12, 26 + i * 26), cv2.FONT_HERSHEY_SIMPLEX, .55, (255, 255, 255), 1)
            if writer is None:
                writer = cv2.VideoWriter(str(args.output), cv2.VideoWriter_fourcc(*"mp4v"), args.fps, (w, h))
                if not writer.isOpened():
                    raise RuntimeError("Could not create output video")
            writer.write(frame)
            total += 1
    finally:
        capture.release()
        if writer is not None:
            writer.release()
    print(json.dumps({"frames": total, "frames_with_unverified_boxes": frames_with_boxes,
                      "elapsed_seconds": round(time.monotonic() - start_clock, 2),
                      "output": str(args.output), "detector": "OpenCV HOG baseline"}))
    if not total:
        raise SystemExit("No frames read; check start time and codec support")


if __name__ == "__main__":
    main()
