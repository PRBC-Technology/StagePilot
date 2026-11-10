"""YOLOX frame inference for the local detection preview."""
import time
import cv2
import numpy as np


class PersonDetector:
    def __init__(self, model, backend='cpu'):
        self.backend = backend
        self.session = None
        if backend == 'directml':
            import onnxruntime as ort
            if 'DmlExecutionProvider' not in ort.get_available_providers():
                raise RuntimeError('DirectML provider unavailable')
            options = ort.SessionOptions()
            options.enable_mem_pattern = False
            options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            self.session = ort.InferenceSession(str(model), sess_options=options,
                                                 providers=['DmlExecutionProvider', 'CPUExecutionProvider'])
            if 'DmlExecutionProvider' not in self.session.get_providers():
                raise RuntimeError('DirectML provider not active')
            self.session.disable_fallback()
            self.input_name = self.session.get_inputs()[0].name
        else:
            self.net = cv2.dnn.readNetFromONNX(str(model))
        self.grid, stride_values = [], []
        for stride in (8, 16, 32):
            x, y = np.meshgrid(np.arange(640 // stride), np.arange(640 // stride))
            self.grid.append(np.stack((x, y), axis=-1).reshape(-1, 2))
            stride_values.extend([stride] * x.size)
        self.grid = np.concatenate(self.grid)
        self.strides = np.array(stride_values)[:, None]

    def detect(self, frame, confidence=0.75):
        h, w = frame.shape[:2]
        ratio = min(640 / h, 640 / w)
        small = cv2.resize(frame, (int(w * ratio), int(h * ratio)))
        padded = np.full((640, 640, 3), 114, dtype=np.uint8)
        padded[:small.shape[0], :small.shape[1]] = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        blob = np.ascontiguousarray(np.transpose(padded.astype(np.float32), (2, 0, 1))[None])
        start = time.perf_counter()
        if self.session is not None:
            raw = self.session.run(None, {self.input_name: blob})[0][0]
        else:
            self.net.setInput(blob)
            raw = self.net.forward()[0]
        infer = time.perf_counter() - start
        centers = (raw[:, :2] + self.grid) * self.strides
        sizes = np.exp(np.clip(raw[:, 2:4], -20, 20)) * self.strides
        scores = raw[:, 4] * raw[:, 5]
        candidates = np.where(scores >= confidence)[0]
        rects = np.concatenate((centers - sizes / 2, sizes), axis=1)[candidates] / ratio
        selected = cv2.dnn.NMSBoxes(rects.tolist(), scores[candidates].tolist(), confidence, .45)
        view = cv2.resize(frame, (960, max(1, int(h * 960 / w))))
        for index in np.asarray(selected).flatten():
            x, y, bw, bh = (int(v * 960 / w) for v in rects[index])
            cv2.rectangle(view, (x, y), (x + bw, y + bh), (64, 220, 100), 2)
            cv2.putText(view, f'person {scores[candidates[index]]:.2f}',
                        (max(0, x), max(18, y - 5)), cv2.FONT_HERSHEY_SIMPLEX,
                        .55, (64, 220, 100), 2)
        return view, len(np.asarray(selected).flatten()), infer
