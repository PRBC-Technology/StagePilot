# StagePilot

StagePilot is a Windows development prototype for detecting people in an RTSP video feed. The local browser preview supports CPU and experimental DirectML inference, an adjustable detection rate and confidence threshold. It does not control a camera or modify OBS.

## Windows setup

Install Git, VS Code and Python, then clone and open the project from PowerShell:

```powershell
git clone https://github.com/PRBC-Technology/PTZ-AutoPilot.git
cd PTZ-AutoPilot
code StagePilot.code-workspace
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install onnxruntime-directml
Invoke-WebRequest -Uri "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/object_detection_yolox/object_detection_yolox_2022nov.onnx" -OutFile "yolox.onnx"
Get-FileHash .\yolox.onnx -Algorithm SHA256
```

The expected model SHA-256 is `C5C2D13E59AE883E6AF3B45DAEA64AF4833A4951C92D116EC270D9DDBE998063`. Do not use the model if the hash differs. DirectML is optional; CPU mode works without it. Open `StagePilot.code-workspace` in VS Code and double-click `Run-StagePilot.bat` to launch the preview.

Enter a camera RTSP URL in the app. The URL is held in memory and not saved by StagePilot; model and video files are excluded from Git. The preview binds to localhost and issues no PTZ commands. Detection can be wrong, and real-time performance depends on the machine and stream. DirectML uses the default graphics adapter and some operations may use CPU.

Run the basic tests using `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`.

## Licence and dependencies

The existing StagePilot code retains its GPL-2.0-only designation and [licence](LICENSE). The separately downloaded [OpenCV Zoo YOLOX model](https://github.com/opencv/opencv_zoo/tree/main/models/object_detection_yolox) is listed as Apache 2.0 by that project. Review licensing compatibility before distributing model and application together. The repository does not contain the model or OBS plugin source.
