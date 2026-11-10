# Architecture

The local browser talks to the Python preview server on loopback. The server reads an RTSP video stream, uses the most recent frame for YOLOX person detection and serves an annotated image. OpenCV CPU and experimental ONNX Runtime DirectML backends are supported. No video is recorded and no PTZ control is implemented. The synthetic controller is separate from the live preview.

Future work: persistent presenter selection, measured latency and frame age, simulated motion, manual override, loss and disconnect handling, and a separately designed camera-control integration. Do not enable physical motion before these have been tested with a simulator and an operator.
