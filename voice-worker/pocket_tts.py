"""Local Pocket TTS worker used by the Jarvis desktop app."""

from __future__ import annotations

import json
import sys
import wave
from pathlib import Path
from typing import Any

import numpy as np
from pocket_tts import TTSModel, export_model_state


MAX_TEXT_CHARS = 3000


def emit(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def load_model() -> TTSModel:
    # Jarvis selects Portuguese explicitly; the sample still provides the voice.
    return TTSModel.load_model(language="portuguese")


def prepare(reference_audio: Path, voice_state_path: Path) -> None:
    model = load_model()
    voice_state = model.get_state_for_audio_prompt(str(reference_audio), truncate=True)
    export_model_state(voice_state, str(voice_state_path))


def write_wav(path: Path, sample_rate: int, audio: np.ndarray) -> None:
    samples = np.asarray(audio, dtype=np.float32).reshape(-1)
    if samples.size == 0:
        raise RuntimeError("O modelo não gerou áudio.")
    pcm = np.rint(np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm.tobytes())


def serve(voice_state_path: Path) -> None:
    model = load_model()
    voice_state = model.get_state_for_audio_prompt(str(voice_state_path))
    emit({"type": "ready", "sample_rate": int(model.sample_rate)})

    for line in sys.stdin:
        request_id = None
        try:
            request = json.loads(line)
            request_id = request.get("id")
            text = request.get("text", "")
            output_path = Path(request.get("output_path", ""))
            if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARS:
                raise ValueError("O texto precisa ter entre 1 e 3000 caracteres.")
            if not output_path.is_absolute():
                raise ValueError("Caminho de áudio temporário inválido.")

            chunks = []
            for chunk in model.generate_audio_stream(voice_state, text.strip()):
                samples = chunk.detach().cpu().numpy().astype(np.float32, copy=False).reshape(-1)
                if samples.size:
                    chunks.append(samples)
            audio = np.concatenate(chunks) if chunks else np.zeros((0,), dtype=np.float32)
            write_wav(output_path, int(model.sample_rate), audio)
            emit({"type": "done", "id": request_id, "sample_rate": int(model.sample_rate)})
        except Exception as error:  # keep the long-running worker usable after a failed utterance
            emit({"type": "error", "id": locals().get("request_id"), "message": str(error)[:400]})


def main() -> int:
    if len(sys.argv) < 2:
        print("Use --prepare ou --serve.", file=sys.stderr)
        return 2

    mode = sys.argv[1]
    try:
        if mode == "--prepare" and len(sys.argv) == 4:
            prepare(Path(sys.argv[2]), Path(sys.argv[3]))
            return 0
        if mode == "--serve" and len(sys.argv) == 3:
            serve(Path(sys.argv[2]))
            return 0
        print("Argumentos inválidos para o worker de voz.", file=sys.stderr)
        return 2
    except Exception as error:
        print(f"Falha no Pocket TTS local: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
