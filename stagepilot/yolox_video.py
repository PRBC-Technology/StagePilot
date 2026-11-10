"""Experimental offline YOLOX preview; no PTZ output. Requires a local ONNX model."""
import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('video', type=Path)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--output', type=Path, default=Path('yolox-preview.mp4'))
    p.add_argument('--start', type=float, default=600)
    p.add_argument('--duration', type=float, default=5)
    p.add_argument('--fps', type=float, default=2)
    p.add_argument('--device', choices=('cpu', 'cuda'), default='cpu')
    args = p.parse_args()
    if args.start < 0 or args.duration <= 0 or not 0 < args.fps <= 30:
        p.error('invalid start, duration or fps')
    if not args.video.is_file() or not args.model.is_file():
        p.error('video and model must be existing local files')
    if args.output.exists() or args.output.resolve() in (args.video.resolve(), args.model.resolve()):
        p.error('output must be a new file')
    targets = cv2.dnn.getAvailableTargets(cv2.dnn.DNN_BACKEND_CUDA)
    if args.device == 'cuda' and cv2.dnn.DNN_TARGET_CUDA not in targets:
        p.error('CUDA DNN is unavailable in this OpenCV build; no CPU fallback used')
    net = cv2.dnn.readNetFromONNX(str(args.model))
    if args.device == 'cuda':
        net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
        net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
    grids, strides = [], []
    for stride in (8, 16, 32):
        x, y = np.meshgrid(np.arange(640 // stride), np.arange(640 // stride))
        grids.append(np.stack((x, y), axis=-1).reshape(-1, 2))
        strides.extend([stride] * x.size)
    grid, stride = np.concatenate(grids), np.array(strides)[:, None]
    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        raise SystemExit('Could not open video')
    video_fps = cap.get(cv2.CAP_PROP_FPS)
    if video_fps <= 0:
        raise SystemExit('Video frame rate unavailable')
    cap.set(cv2.CAP_PROP_POS_MSEC, args.start * 1000)
    writer = None
    frame_index = count = boxes_total = 0
    inference_time = 0.0
    begin = time.perf_counter()
    try:
        while frame_index / video_fps < args.duration:
            ok, frame = cap.read()
            if not ok:
                break
            sample_due = int(frame_index * args.fps / video_fps)
            frame_index += 1
            if sample_due < count:
                continue
            h, w = frame.shape[:2]
            ratio = min(640 / h, 640 / w)
            small = cv2.resize(frame, (int(w * ratio), int(h * ratio)))
            padded = np.full((640, 640, 3), 114, dtype=np.uint8)
            padded[:small.shape[0], :small.shape[1]] = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            blob = np.transpose(padded.astype(np.float32), (2, 0, 1))[None]
            net.setInput(blob)
            t = time.perf_counter()
            raw = net.forward()[0]
            inference_time += time.perf_counter() - t
            centres = (raw[:, :2] + grid) * stride
            sizes = np.exp(np.clip(raw[:, 2:4], -20, 20)) * stride
            scores = raw[:, 4] * raw[:, 5]
            chosen = np.where(scores >= .5)[0]
            rects = np.concatenate((centres - sizes / 2, sizes), axis=1)[chosen] / ratio
            selected = cv2.dnn.NMSBoxes(rects.tolist(), scores[chosen].tolist(), .5, .45)
            view = cv2.resize(frame, (960, int(h * 960 / w)))
            for idx in np.asarray(selected).flatten():
                x, y, bw, bh = rects[idx] * (960 / w)
                x, y, bw, bh = map(int, (x, y, bw, bh))
                cv2.rectangle(view, (x, y), (x + bw, y + bh), (0, 255, 0), 2)
                cv2.putText(view, f'person {scores[chosen[idx]]:.2f}', (max(0, x), max(18, y - 5)), cv2.FONT_HERSHEY_SIMPLEX, .55, (0, 255, 0), 2)
                boxes_total += 1
            cv2.putText(view, 'OFFLINE DETECTIONS | NO CAMERA CONTROL', (10, 25), cv2.FONT_HERSHEY_SIMPLEX, .6, (255, 255, 255), 2)
            if writer is None:
                writer = cv2.VideoWriter(str(args.output), cv2.VideoWriter_fourcc(*'mp4v'), args.fps, (view.shape[1], view.shape[0]))
                if not writer.isOpened():
                    raise RuntimeError('Could not create output')
            writer.write(view)
            count += 1
    finally:
        cap.release()
        if writer is not None:
            writer.release()
    print(json.dumps({'device_requested': args.device, 'sampled_frames': count, 'person_boxes_unverified': boxes_total,
                      'inference_fps': round(count / inference_time, 2) if inference_time else None,
                      'elapsed_seconds': round(time.perf_counter() - begin, 2), 'output': str(args.output)}))
    if count == 0:
        raise SystemExit('No frames decoded')


if __name__ == '__main__':
    main()
