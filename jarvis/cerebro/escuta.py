"""Escuta do microfone para a janela: nível em tempo real, fim por silêncio e transcrição no servidor de voz."""

import array
import ctypes
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


def _morrer_com_o_pai() -> None:
    """No processo do gravador: se o cérebro morrer, o kernel encerra o gravador junto (sem órfãos gravando)."""
    PR_SET_PDEATHSIG = 1
    ctypes.CDLL("libc.so.6", use_errno=True).prctl(PR_SET_PDEATHSIG, signal.SIGTERM)


def _inicio_dados(cabecalho: bytes) -> int | None:
    posicao = cabecalho.find(b"data")
    return None if posicao < 0 else posicao + 8


class Escuta:
    def __init__(self, ao_nivel: Callable[[float], None], ao_fim: Callable[[str | None], None],
                 chamar=voz_cliente.chamar, comando: list[str] | None = None):
        self._ao_nivel, self._ao_fim, self._chamar = ao_nivel, ao_fim, chamar
        self._comando = comando
        self._proc: subprocess.Popen | None = None
        self._proc_pronto = threading.Event()
        self._erro_gravador: OSError | None = None
        self._encerrar = threading.Event()
        self._cancelada = False
        self._trava = threading.Lock()
        self.ativa = False

    def iniciar(self) -> None:
        with self._trava:
            if self.ativa:
                return
            self.ativa = True
        self._encerrar.clear()
        self._cancelada = False
        self._chamar("/parar")
        self._chamar("/ouvindo", {"ligado": True})
        arquivo = dados() / "escuta.wav"
        arquivo.unlink(missing_ok=True)
        comando = self._comando or ["pw-record", "--rate", str(TAXA), "--channels", "1", "--format", "s16",
                                    str(arquivo)]
        self._proc_pronto.clear()
        self._erro_gravador = None
        threading.Thread(target=self._abrir_gravador, args=(comando,), daemon=True).start()
        self._proc_pronto.wait()
        if self._erro_gravador:
            print(f"cérebro: não iniciou pw-record: {self._erro_gravador}", flush=True)
            self._chamar("/ouvindo", {"ligado": False})
            self.ativa = False
            self._ao_fim(None)
            return
        threading.Thread(target=self._acompanhar, args=(arquivo,), daemon=True).start()

    def _abrir_gravador(self, comando: list[str]) -> None:
        """Mantém viva a thread que criou `pw-record` até o gravador terminar.

        No Linux, PR_SET_PDEATHSIG acompanha a thread criadora, não o processo inteiro.
        `iniciar()` costuma rodar numa thread HTTP curta; esta thread dona evita que o
        gravador receba SIGTERM assim que a requisição Super+J termina.
        """
        try:
            # Deixa diagnósticos do PipeWire chegarem ao journal do serviço.
            self._proc = subprocess.Popen(comando, stdout=subprocess.DEVNULL, preexec_fn=_morrer_com_o_pai)
        except OSError as erro:
            self._erro_gravador = erro
        finally:
            self._proc_pronto.set()
        if self._proc:
            self._proc.wait()

    def encerrar(self) -> None:
        self._encerrar.set()

    def cancelar(self) -> None:
        """Para de ouvir na hora e descarta o que gravou (o senhor fechou a janela)."""
        self._cancelada = True
        self._encerrar.set()

    def _acompanhar(self, arquivo) -> None:
        texto = None
        try:
            texto = self._ouvir(arquivo)
        finally:
            # Sempre libera a voz (pausada enquanto ouvia) e encerra, mesmo se algo falhou.
            self._parar_gravacao()
            self._chamar("/ouvindo", {"ligado": False})
            self.ativa = False
            self._ao_fim(texto)

    def _ouvir(self, arquivo) -> str | None:
        detector = DetectorSilencio()
        inicio = time.time()
        offset = None
        inicio_audio = None
        resultado = None
        while resultado is None:
            if self._encerrar.wait(0.1):
                resultado = "fim"
                break
            if self._proc and self._proc.poll() is not None:
                print(f"cérebro: pw-record encerrou durante a escuta (código {self._proc.returncode})", flush=True)
                return None
            novo = b""
            try:
                with arquivo.open("rb") as f:
                    if offset is None:
                        inicio_audio = _inicio_dados(f.read(4096))
                        offset = inicio_audio
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
        self._parar_gravacao()
        if resultado != "fim" or self._cancelada or offset is None or not arquivo.exists():
            return None
        # `offset` é o cursor de leitura, que no fim já aponta para o fim do PCM.
        # A duração precisa usar o início dos dados do WAV, não o cursor avançado.
        duracao = max(0, arquivo.stat().st_size - (inicio_audio or 44)) / BYTES_POR_SEGUNDO
        resposta = self._chamar("/transcrever", {"caminho": str(arquivo)}, timeout=30.0)
        return transcricao_util(resposta.get("texto", ""), duracao) if resposta else None

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
