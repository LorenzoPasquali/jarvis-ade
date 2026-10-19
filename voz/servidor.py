"""Servidor local de voz do Jarvis: fala com OmniVoice (voz clonada do MP3) e transcreve com Whisper.

Roda no venv do OmniVoice. Os modelos ficam carregados na GPU entre as falas.
HTTP em 127.0.0.1:8765: POST /falar, /parar, /mudo, /transcrever; GET /saude.
"""

import io
import json
import os
import queue
import subprocess
import sys
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis.config import MP3_REFERENCIA, TEXTO_REFERENCIA, VOZ_PORTA, dados  # noqa: E402
from jarvis.texto_fala import dividir_frases  # noqa: E402


def _log(mensagem: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {mensagem}", file=sys.stderr, flush=True)


class Locutor:
    """Fila de falas: gera a frase seguinte enquanto a atual toca; `parar()` descarta tudo."""

    def __init__(self, motor, tocador):
        self.motor, self.tocador = motor, tocador
        self.mudo = False
        self._ouvindo_ate = 0.0
        self._geracao = 0
        self._falando = False
        self._frases: queue.Queue = queue.Queue()
        self._audios: queue.Queue = queue.Queue(maxsize=1)
        threading.Thread(target=self._gerar, daemon=True).start()
        threading.Thread(target=self._tocar, daemon=True).start()

    def falar(self, texto: str) -> None:
        if self.mudo or not texto.strip():
            return
        _log(f"recebido: {texto[:80]!r}")
        for frase in dividir_frases(texto):
            self._frases.put((self._geracao, frase))

    def parar(self) -> None:
        self._geracao += 1
        for fila in (self._frases, self._audios):
            while True:
                try:
                    fila.get_nowait()
                except queue.Empty:
                    break
        self.tocador.parar()

    def ouvindo(self, ligado: bool, limite_s: float = 120.0) -> None:
        """Segura a reprodução enquanto o usuário grava (com limite, caso o fim nunca chegue)."""
        self._ouvindo_ate = time.time() + limite_s if ligado else 0.0

    def estado(self) -> dict:
        return {"falando": self._falando, "fila": self._frases.qsize() + self._audios.qsize(), "mudo": self.mudo}

    def _gerar(self) -> None:
        while True:
            geracao, frase = self._frases.get()
            if geracao != self._geracao:
                continue
            try:
                audio = self.motor.sintetizar(frase)
            except Exception as erro:
                _log(f"falha ao sintetizar: {erro!r}")
                continue
            if geracao == self._geracao:
                self._audios.put((geracao, audio))

    def _tocar(self) -> None:
        while True:
            geracao, audio = self._audios.get()
            while time.time() < self._ouvindo_ate and geracao == self._geracao:
                time.sleep(0.05)
            if geracao != self._geracao:
                continue
            self._falando = True
            _log("tocando")
            try:
                self.tocador.tocar(audio)
            except Exception as erro:
                _log(f"falha ao tocar: {erro!r}")
            finally:
                self._falando = not self._audios.empty()


class TocadorPw:
    def __init__(self):
        self._processo: subprocess.Popen | None = None
        self._trava = threading.Lock()

    def tocar(self, wav: bytes) -> None:
        arquivo = dados() / "voz" / "fala.wav"
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_bytes(wav)
        with self._trava:
            self._processo = subprocess.Popen(["pw-play", str(arquivo)])
        self._processo.wait()

    def parar(self) -> None:
        with self._trava:
            if self._processo and self._processo.poll() is None:
                self._processo.kill()


class MotorOmniVoice:
    def __init__(self):
        import torch
        from omnivoice import OmniVoice, VoiceClonePrompt

        self._modelo = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map="cuda:0", dtype=torch.float16)
        arquivo = dados() / "voz" / "jarvis-prompt.pt"
        if arquivo.exists():
            self._prompt = VoiceClonePrompt.load(str(arquivo))
        else:
            arquivo.parent.mkdir(parents=True, exist_ok=True)
            self._prompt = self._modelo.create_voice_clone_prompt(
                ref_audio=str(MP3_REFERENCIA), ref_text=TEXTO_REFERENCIA)
            self._prompt.save(str(arquivo))

    def sintetizar(self, frase: str) -> bytes:
        import numpy as np

        audio = self._modelo.generate(text=frase, voice_clone_prompt=self._prompt)[0]
        pcm = (np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0) * 32767).astype("<i2")
        saida = io.BytesIO()
        with wave.open(saida, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(pcm.tobytes())
        return saida.getvalue()


class TranscritorWhisper:
    def __init__(self):
        import torch
        from transformers import pipeline

        self._pipeline = pipeline("automatic-speech-recognition", model="openai/whisper-large-v3-turbo",
                                  dtype=torch.float16, device="cuda:0")

    def transcrever(self, caminho: str) -> str:
        resultado = self._pipeline(caminho, generate_kwargs={"task": "transcribe", "language": "portuguese"})
        return (resultado.get("text") or "").strip()


def criar_servidor(locutor: Locutor, transcritor, porta: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _responder(self, codigo: int, corpo: dict) -> None:
            dados_json = json.dumps(corpo, ensure_ascii=False).encode()
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(dados_json)))
            self.end_headers()
            self.wfile.write(dados_json)

        def do_GET(self):
            if self.path == "/saude":
                self._responder(200, {"ok": True, **locutor.estado()})
            else:
                self._responder(404, {"erro": "rota desconhecida"})

        def do_POST(self):
            tamanho = int(self.headers.get("Content-Length") or 0)
            try:
                corpo = json.loads(self.rfile.read(tamanho) or b"{}")
                if not isinstance(corpo, dict):
                    raise ValueError
            except ValueError:
                self._responder(400, {"erro": "corpo JSON inválido"})
                return
            if self.path == "/falar":
                locutor.falar(str(corpo.get("texto") or ""))
                self._responder(202, {"ok": True})
            elif self.path == "/parar":
                locutor.parar()
                self._responder(200, {"ok": True})
            elif self.path == "/mudo":
                locutor.mudo = bool(corpo.get("ligado"))
                if locutor.mudo:
                    locutor.parar()
                self._responder(200, {"ok": True, "mudo": locutor.mudo})
            elif self.path == "/ouvindo":
                locutor.ouvindo(bool(corpo.get("ligado")))
                self._responder(200, {"ok": True})
            elif self.path == "/transcrever":
                try:
                    self._responder(200, {"texto": transcritor.transcrever(str(corpo.get("caminho") or ""))})
                except Exception as erro:
                    self._responder(500, {"erro": repr(erro)})
            else:
                self._responder(404, {"erro": "rota desconhecida"})

    return ThreadingHTTPServer(("127.0.0.1", porta), Handler)


def main() -> None:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    _log("carregando OmniVoice e Whisper na GPU")
    locutor = Locutor(MotorOmniVoice(), TocadorPw())
    servidor = criar_servidor(locutor, TranscritorWhisper(), VOZ_PORTA)
    _log(f"pronto em 127.0.0.1:{VOZ_PORTA}")
    servidor.serve_forever()


if __name__ == "__main__":
    main()
