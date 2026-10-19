import json
import os
import sys

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import torch
from transformers import pipeline
from transformers.utils import logging

logging.set_verbosity_error()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(2)

    recognizer = pipeline(
        "automatic-speech-recognition",
        model="openai/whisper-large-v3-turbo",
        dtype=torch.float32,
        device="cpu",
    )
    result = recognizer(
        sys.argv[1],
        generate_kwargs={"task": "transcribe", "language": "portuguese"},
    )
    print(json.dumps({"text": result.get("text", "").strip()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
