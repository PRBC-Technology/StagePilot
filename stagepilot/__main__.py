"""Run a deterministic, completely offline simulation."""
from dataclasses import asdict
import json

from .controller import Detection, recommend


def main() -> None:
    samples = [Detection(0.5, 0.45, 0.45, 0.95),
               Detection(0.8, 0.45, 0.30, 0.9),
               Detection(0.65, 0.55, 0.50, 0.4), None]
    for index, sample in enumerate(samples):
        print(json.dumps({"frame": index, "detection": asdict(sample) if sample else None,
                          "simulated_motion": asdict(recommend(sample))}))


if __name__ == "__main__":
    main()
