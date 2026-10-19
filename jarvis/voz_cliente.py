"""Lado cliente da voz: hook que fala as respostas, aperta-e-fala, calar e mudo."""

import json
import os
import re
import signal
import subprocess
import time
import traceback
import unicodedata
import urllib.error
import urllib.request
import wave
from datetime import datetime

from jarvis import orca, sessao
from jarvis.config import VOZ_URL, dados
from jarvis.orca import OrcaErro
from jarvis.texto_fala import extrair_fala

_ALUCINACOES = ["legendas pela comunidade amara.org", "obrigado", "obrigada", "obrigado por assistir",
                "tchau", "inscreva-se no canal"]
_DURACAO_MINIMA = 0.5


def chamar(rota: str, corpo: dict | None = None, timeout: float = 3.0) -> dict | None:
    dados_json = None if rota == "/saude" else json.dumps(corpo or {}).encode()
    req = urllib.request.Request(VOZ_URL + rota, data=dados_json, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resposta:
            return json.loads(resposta.read() or b"{}")
    except (OSError, urllib.error.URLError, ValueError):
        return None


def _log_hook(mensagem: str) -> None:
    with (dados() / "hook.log").open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')} {mensagem}\n")


def hook_fala(entrada_json: str, chamar=chamar) -> None:
    try:
        mensagem = json.loads(entrada_json).get("last_assistant_message") or ""
        fala = extrair_fala(mensagem)
        if fala:
            chamar("/falar", {"texto": fala})
    except Exception:
        try:
            _log_hook(traceback.format_exc())
        except OSError:
            pass


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^\w\s]", "", sem_acento).casefold().strip()


def transcricao_util(texto: str, duracao_s: float) -> str | None:
    texto = (texto or "").strip()
    normalizado = _normalizar(texto)
    if duracao_s < _DURACAO_MINIMA or not normalizado:
        return None
    if normalizado in {_normalizar(a) for a in _ALUCINACOES}:
        return None
    return texto


class GravadorPw:
    """Grava o microfone com pw-record num processo que sobrevive entre as duas chamadas de `ouvir`."""

    def iniciar(self, caminho) -> int:
        processo = subprocess.Popen(["pw-record", "--rate", "16000", "--channels", "1", str(caminho)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return processo.pid

    def ativo(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                return b"pw-record" in f.read()
        except OSError:
            return False

    def encerrar(self, pid: int) -> float:
        os.kill(pid, signal.SIGINT)
        for _ in range(50):
            if not self.ativo(pid):
                break
            time.sleep(0.05)
        try:
            with wave.open(str(dados() / "ptt.wav"), "rb") as w:
                return w.getnframes() / float(w.getframerate())
        except (OSError, wave.Error, EOFError):
            return 0.0


def notify_send(mensagem: str) -> None:
    try:
        subprocess.run(["notify-send", "-a", "Jarvis", "-t", "2500", "Jarvis", mensagem], timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass


def ouvir(gravador, chamar=chamar, executar=orca.executar, notificar=notify_send) -> str:
    estado_ptt = dados() / "ptt.json"
    try:
        gravando = json.loads(estado_ptt.read_text())
    except (FileNotFoundError, ValueError):
        gravando = None

    if not gravando or not gravador.ativo(gravando["pid"]):
        if chamar("/parar") is None:
            notificar("Servidor de voz indisponível.")
            return "sem_voz"
        pid = gravador.iniciar(dados() / "ptt.wav")
        estado_ptt.write_text(json.dumps({"pid": pid, "inicio": time.time()}))
        notificar("Jarvis ouvindo…")
        return "gravando"

    duracao = gravador.encerrar(gravando["pid"])
    estado_ptt.unlink(missing_ok=True)
    resposta = chamar("/transcrever", {"caminho": str(dados() / "ptt.wav")}, timeout=30.0)
    if resposta is None:
        notificar("Servidor de voz indisponível.")
        return "sem_voz"
    texto = transcricao_util(resposta.get("texto", ""), duracao)
    if texto is None:
        notificar("Não entendi, senhor.")
        return "descartado"
    registro = sessao.ler()
    if not registro:
        notificar("Sessão do Jarvis não está aberta.")
        return "sem_sessao"
    try:
        executar(["terminal", "send", "--terminal", registro["terminal"], "--text", f"[voz] {texto}", "--enter"])
    except OrcaErro:
        notificar("Sessão do Jarvis não está aberta.")
        return "sem_sessao"
    notificar(texto)
    return "enviado"


def calar(chamar=chamar) -> None:
    chamar("/parar")


def mudo(ligado: bool, chamar=chamar) -> None:
    chamar("/mudo", {"ligado": ligado})
