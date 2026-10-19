"""Escuta do microfone para a janela: nível em tempo real, fim por silêncio e transcrição no servidor de voz."""

import array
import math
import signal
import subprocess
import threading
import time
from collections.abc import Callable

from jarvis import voz_cliente
from jarvis.config import dados
from jarvis.voz_cliente import transcricao_util

TAXA = 16000
BYTES_POR_SEGUNDO = TAXA * 2


def rms(pcm: bytes) -> float:
    amostras = array.array("h")
    amostras.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    if not amostras:
        return 0.0
    return math.sqrt(sum(a * a for a in amostras) / len(amostras)) / 32768.0


class DetectorSilencio:
    """Decide quando parar de ouvir. `t` = segundos desde o início da gravação.

    O limiar acompanha o ruído do microfone: `fator` vezes o menor nível já visto (nunca abaixo de
    `limiar_minimo`), reavaliado sobre todo o histórico — assim uma fala logo no início, antes de o piso
    ser conhecido, ainda conta.
    """

    def __init__(self, limiar_minimo: float = 0.008, fator: float = 3.0, silencio_s: float = 1.0,
                 espera_fala_s: float = 6.0, maximo_s: float = 30.0, blocos_minimos: int = 3):
        self.limiar_minimo, self.fator, self.blocos_minimos = limiar_minimo, fator, blocos_minimos
        self.silencio_s, self.espera_fala_s, self.maximo_s = silencio_s, espera_fala_s, maximo_s
        self._historico: list[tuple[float, float]] = []

    def alimentar(self, nivel: float | None, t: float) -> str | None:
        """`nivel=None`: nenhum áudio novo nesta leitura — só o relógio anda (não derruba o piso do ruído)."""
        if nivel is not None:
            self._historico.append((t, nivel))
        if not self._historico:
            return "vazio" if t >= self.espera_fala_s else None
        piso = min(n for _, n in self._historico)
        limiar = max(self.limiar_minimo, piso * self.fator)
        sons = [instante for instante, n in self._historico if n >= limiar]
        falou = len(sons) >= self.blocos_minimos  # estalos isolados não são fala
        if t >= self.maximo_s:
            return "fim" if falou else "vazio"
        if falou and t - sons[-1] >= self.silencio_s:
            return "fim"
        if not falou and t >= self.espera_fala_s:
            return "vazio"
        return None


def _inicio_dados(cabecalho: bytes) -> int | None:
    posicao = cabecalho.find(b"data")
    return None if posicao < 0 else posicao + 8


class Escuta:
    def __init__(self, ao_nivel: Callable[[float], None], ao_fim: Callable[[str | None], None],
                 chamar=voz_cliente.chamar, comando: list[str] | None = None):
        self._ao_nivel, self._ao_fim, self._chamar = ao_nivel, ao_fim, chamar
        self._comando = comando
        self._proc: subprocess.Popen | None = None
        self._encerrar = threading.Event()
        self.ativa = False

    def iniciar(self) -> None:
        if self.ativa:
            return
        self.ativa = True
        self._encerrar.clear()
        self._chamar("/parar")
        self._chamar("/ouvindo", {"ligado": True})
        arquivo = dados() / "escuta.wav"
        arquivo.unlink(missing_ok=True)
        comando = self._comando or ["pw-record", "--rate", str(TAXA), "--channels", "1", "--format", "s16",
                                    str(arquivo)]
        self._proc = subprocess.Popen(comando, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        threading.Thread(target=self._acompanhar, args=(arquivo,), daemon=True).start()

    def encerrar(self) -> None:
        self._encerrar.set()

    def _acompanhar(self, arquivo) -> None:
        detector = DetectorSilencio()
        inicio = time.time()
        offset = None
        resultado = None
        while resultado is None:
            if self._encerrar.wait(0.1):
                resultado = "fim"
                break
            novo = b""
            try:
                with arquivo.open("rb") as f:
                    if offset is None:
                        offset = _inicio_dados(f.read(4096))
                    if offset is not None:
                        f.seek(offset)
                        novo = f.read()
            except FileNotFoundError:
                pass
            novo = novo[: len(novo) - len(novo) % 2]
            nivel = None
            if novo:
                offset += len(novo)
                nivel = rms(novo)
                self._ao_nivel(nivel)
            resultado = detector.alimentar(nivel, time.time() - inicio)
        texto = None
        try:
            self._parar_gravacao()
            if resultado == "fim" and offset is not None and arquivo.exists():
                duracao = max(0, arquivo.stat().st_size - offset) / BYTES_POR_SEGUNDO
                resposta = self._chamar("/transcrever", {"caminho": str(arquivo)}, timeout=30.0)
                if resposta:
                    texto = transcricao_util(resposta.get("texto", ""), duracao)
        finally:
            # Sempre libera a voz (pausada enquanto ouvia) e encerra, mesmo se a gravação falhou.
            self._chamar("/ouvindo", {"ligado": False})
            self.ativa = False
            self._ao_fim(texto)

    def _parar_gravacao(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.send_signal(signal.SIGINT)
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()


def tela_bloqueada(runner=subprocess.run) -> bool:
    try:
        proc = runner(["gdbus", "call", "--session", "--dest", "org.gnome.ScreenSaver",
                       "--object-path", "/org/gnome/ScreenSaver", "--method", "org.gnome.ScreenSaver.GetActive"],
                      capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "true" in (proc.stdout or "")
