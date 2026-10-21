"""Ouvido: escuta "Jarvis" o tempo todo, como uma Alexa — tudo local, sem conta nem chave.

Um recortador leve (nível de áudio, na CPU) separa cada frase falada no microfone. Só as frases vão ao Whisper que o
servidor de voz já mantém na GPU, e só os primeiros tokens são decodificados para ver se a frase começa com "Jarvis".
Se começar, a frase inteira é transcrita: "Jarvis, como está o app de saúde?" já vira a pergunta.
"""

import difflib
import re
import subprocess
import threading
import time
import unicodedata
import wave
from collections import deque
from collections.abc import Callable

from jarvis import voz_cliente
from jarvis.cerebro.escuta import _morrer_com_o_pai, rms
from jarvis.config import dados

TAXA = 16000
BLOCO_S = 0.1
BYTES_BLOCO = int(TAXA * BLOCO_S) * 2
TOKENS_CONFERIR = 8
MAX_POR_MINUTO = 20  # TV ou conversa sem parar não deixam a GPU transcrevendo o tempo todo
ESPERA_REINICIO_S = 3.0


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def depois_de_jarvis(texto: str) -> str | None:
    """O que o senhor disse depois de "Jarvis" ("" se foi só o nome); None se a frase não chama o Jarvis.

    Vale "Jarvis" entre as três primeiras palavras ("ei, Jarvis", "ok Jarvis") e grafias próximas que o Whisper
    produz ("Járvis", "Jarves", "Djarvis").
    """
    palavras = texto.split()
    for i, palavra in enumerate(palavras[:3]):
        limpa = re.sub(r"[^a-z]", "", _sem_acento(palavra.casefold()))
        if limpa and difflib.SequenceMatcher(None, limpa, "jarvis").ratio() >= 0.8:
            return " ".join(palavras[i + 1:]).lstrip(",.!?:;- ").strip()
    return None


class Recortador:
    """Separa frases num fluxo contínuo de blocos de 100 ms.

    O piso de ruído é o menor nível dos últimos `janela_piso_s`; fala é `fator` vezes isso (nunca abaixo de
    `limiar_minimo`). A frase começa com um pouco de áudio de antes (para não cortar o "Jar") e termina após
    `silencio_s` sem fala. Frases curtas demais (estalos) ou longas demais (TV, conversa) são descartadas.
    """

    def __init__(self, limiar_minimo: float = 0.008, fator: float = 3.0, silencio_s: float = 0.7,
                 minimo_s: float = 0.3, maximo_s: float = 15.0, janela_piso_s: float = 30.0, antes_s: float = 0.3):
        self.limiar_minimo, self.fator = limiar_minimo, fator
        self.silencio, self.minimo = round(silencio_s / BLOCO_S), round(minimo_s / BLOCO_S)
        self.maximo = round(maximo_s / BLOCO_S)
        self._niveis: deque[float] = deque(maxlen=round(janela_piso_s / BLOCO_S))
        self._antes: deque[bytes] = deque(maxlen=round(antes_s / BLOCO_S))
        self._frase: list[bytes] = []
        self._com_fala = 0
        self._quietos = 0
        self._descartando = False

    def alimentar(self, bloco: bytes) -> bytes | None:
        nivel = rms(bloco)
        self._niveis.append(nivel)
        falando = nivel >= max(self.limiar_minimo, min(self._niveis) * self.fator)
        if not self._frase and not self._descartando:
            if falando:
                self._frase, self._com_fala, self._quietos = [*self._antes, bloco], 1, 0
                self._antes.clear()
            else:
                self._antes.append(bloco)
            return None
        if not self._descartando:
            self._frase.append(bloco)
        self._com_fala += falando
        self._quietos = 0 if falando else self._quietos + 1
        if len(self._frase) > self.maximo:
            self._descartando, self._frase = True, []
        if self._quietos < self.silencio:
            return None
        frase, com_fala = self._frase, self._com_fala
        self._frase, self._com_fala, self._quietos, self._descartando = [], 0, 0, False
        return b"".join(frase) if frase and com_fala >= self.minimo else None


def gravar_wav(caminho, pcm: bytes) -> None:
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TAXA)
        w.writeframes(pcm)


class Ouvido:
    def __init__(self, ao_ouvir: Callable[[str], None], pausado: Callable[[], bool] = lambda: False,
                 chamar=voz_cliente.chamar, comando: list[str] | None = None):
        self._ao_ouvir = ao_ouvir
        self._pausado = pausado
        self._chamar = chamar
        self._comando = comando or ["pw-record", "--rate", str(TAXA), "--channels", "1", "--format", "s16", "-"]
        self._parando = threading.Event()
        self._proc: subprocess.Popen | None = None
        self._transcricoes: deque[float] = deque()

    def iniciar(self) -> None:
        # A thread dona do gravador vive tanto quanto ele: PDEATHSIG segue a thread que o criou.
        threading.Thread(target=self._laco, daemon=True).start()
        print("ouvido: escutando \"Jarvis\"", flush=True)

    def parar(self) -> None:
        self._parando.set()
        if self._proc and self._proc.poll() is None:
            self._proc.kill()

    def _laco(self) -> None:
        while not self._parando.is_set():
            try:
                self._proc = subprocess.Popen(self._comando, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                              preexec_fn=_morrer_com_o_pai)
            except OSError as erro:
                print(f"ouvido: não abriu o microfone: {erro}", flush=True)
                self._parando.wait(ESPERA_REINICIO_S)
                continue
            recortador = Recortador()
            while not self._parando.is_set():
                bloco = self._proc.stdout.read(BYTES_BLOCO)
                if len(bloco) < BYTES_BLOCO:  # gravador caiu: abre de novo
                    break
                frase = recortador.alimentar(bloco)
                if frase and not self._pausado():
                    threading.Thread(target=self.conferir, args=(frase,), daemon=True).start()
            if self._proc.poll() is None:
                self._proc.kill()
            self._proc.wait()
            self._parando.wait(ESPERA_REINICIO_S)

    def _dentro_do_limite(self) -> bool:
        agora = time.time()
        while self._transcricoes and agora - self._transcricoes[0] > 60:
            self._transcricoes.popleft()
        if len(self._transcricoes) >= MAX_POR_MINUTO:
            return False
        self._transcricoes.append(agora)
        return True

    def conferir(self, frase: bytes) -> None:
        if not self._dentro_do_limite():
            return
        arquivo = dados() / f"ouvido-{threading.get_ident()}.wav"
        try:
            gravar_wav(arquivo, frase)
            rapido = self._chamar("/transcrever", {"caminho": str(arquivo), "max_tokens": TOKENS_CONFERIR},
                                  timeout=10.0) or {}
            resto = depois_de_jarvis(rapido.get("texto", ""))
            if resto is None:
                return
            if resto or len(frase) / (TAXA * 2) > 1.5:  # tem mais coisa depois do nome: a frase inteira
                inteira = self._chamar("/transcrever", {"caminho": str(arquivo)}, timeout=30.0) or {}
                resto = depois_de_jarvis(inteira.get("texto", "")) or resto
            print(f"ouvido: chamado (\"{resto[:60]}\")", flush=True)
            self._ao_ouvir(resto)
        finally:
            arquivo.unlink(missing_ok=True)
