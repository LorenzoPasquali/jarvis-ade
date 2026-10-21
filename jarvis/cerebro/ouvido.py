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
from jarvis.voz_cliente import transcricao_util

TAXA = 16000
BLOCO_S = 0.1
BYTES_BLOCO = int(TAXA * BLOCO_S) * 2
TOKENS_CONFERIR = 8
SILENCIO_S = 0.7  # fim de frase quando o ouvido só espera o "Jarvis"
SILENCIO_PERGUNTA_S = 1.0  # depois do "Jarvis", pausas no meio da pergunta não a cortam
ESPERA_PERGUNTA_S = 8.0  # depois do "Jarvis" sozinho, quanto tempo espera o senhor começar a pergunta
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

    def __init__(self, limiar_minimo: float = 0.008, fator: float = 3.0, silencio_s: float = SILENCIO_S,
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
        self.nivel = 0.0

    @property
    def em_frase(self) -> bool:
        return bool(self._frase) or self._descartando

    def alimentar(self, bloco: bytes) -> bytes | None:
        nivel = self.nivel = rms(bloco)
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
    """Lê o microfone sem parar. Frase que começa com "Jarvis" chama o cérebro (`ao_chamar`).

    "Jarvis" sozinho deixa o ouvido esperando a pergunta: a próxima frase que o senhor começar (depois do "Jarvis" ou
    da saudação) é transcrita inteira e vai para `ao_perguntar`. Como o microfone nunca fecha, nada da pergunta se
    perde enquanto o "Jarvis" é conferido ou a janela abre.
    `ao_chamar(resto)` devolve None (não esperar pergunta) ou o instante a partir do qual o áudio já é do senhor
    (fim da saudação; 0 = logo depois do "Jarvis").
    """

    def __init__(self, ao_chamar: Callable[[str], float | None],
                 ao_perguntar: Callable[[str | None], None] = lambda texto: None,
                 pausado: Callable[[], bool] = lambda: False, chamar=voz_cliente.chamar,
                 comando: list[str] | None = None, ao_nivel: Callable[[float], None] = lambda nivel: None):
        self._ao_chamar, self._ao_perguntar, self._ao_nivel = ao_chamar, ao_perguntar, ao_nivel
        self._pausado = pausado
        self._chamar = chamar
        self._comando = comando or ["pw-record", "--rate", str(TAXA), "--channels", "1", "--format", "s16", "-"]
        self._parando = threading.Event()
        self._proc: subprocess.Popen | None = None
        self._transcricoes: deque[float] = deque()
        self._trava = threading.Lock()
        self._pergunta_desde = 0.0
        self._pergunta_ate = 0.0  # 0: não está esperando pergunta

    def iniciar(self) -> None:
        # A thread dona do gravador vive tanto quanto ele: PDEATHSIG segue a thread que o criou.
        threading.Thread(target=self._laco, daemon=True).start()
        print("ouvido: escutando \"Jarvis\"", flush=True)

    def parar(self) -> None:
        self._parando.set()
        if self._proc and self._proc.poll() is None:
            self._proc.kill()

    @property
    def esperando_pergunta(self) -> bool:
        return self._pergunta_ate > 0

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
                self.processar(recortador, bloco, time.time())
            if self._proc.poll() is None:
                self._proc.kill()
            self._proc.wait()
            self._parando.wait(ESPERA_REINICIO_S)

    def processar(self, recortador: Recortador, bloco: bytes, agora: float) -> None:
        esperando = self.esperando_pergunta
        recortador.silencio = round((SILENCIO_PERGUNTA_S if esperando else SILENCIO_S) / BLOCO_S)
        estava_em_frase = recortador.em_frase
        frase = recortador.alimentar(bloco)
        if not estava_em_frase and recortador.em_frase:
            self._inicio_fala = agora  # sem contar o áudio de antes que o recortador guarda
        if esperando:
            self._ao_nivel(recortador.nivel)
            if not recortador.em_frase and frase is None and agora > self._pergunta_ate:
                self._encerrar_espera(None)
                return
        if frase is None or self._pausado():
            return
        inicio = getattr(self, "_inicio_fala", agora)
        if esperando and inicio >= self._pergunta_desde:
            self._encerrar_espera(frase)
        elif not esperando:
            threading.Thread(target=self.conferir, args=(frase, agora), daemon=True).start()
        # esperando, mas a frase começou antes (a própria saudação): ignora

    def _encerrar_espera(self, frase: bytes | None) -> None:
        with self._trava:
            if not self.esperando_pergunta:
                return
            self._pergunta_ate = 0.0
        if frase is None:
            print("ouvido: o senhor não perguntou nada", flush=True)
            self._ao_perguntar(None)
        else:
            threading.Thread(target=self._transcrever_pergunta, args=(frase,), daemon=True).start()

    def _transcrever_pergunta(self, frase: bytes) -> None:
        texto = self._transcrever(frase)
        texto = transcricao_util(texto or "", len(frase) / (TAXA * 2))
        print(f"ouvido: pergunta {texto[:60]!r}" if texto else "ouvido: pergunta vazia", flush=True)
        self._ao_perguntar(texto)

    def _transcrever(self, frase: bytes, max_tokens: int | None = None) -> str | None:
        arquivo = dados() / f"ouvido-{threading.get_ident()}.wav"
        try:
            gravar_wav(arquivo, frase)
            corpo = {"caminho": str(arquivo)}
            if max_tokens:
                corpo["max_tokens"] = max_tokens
            resposta = self._chamar("/transcrever", corpo, timeout=10.0 if max_tokens else 30.0)
            return (resposta or {}).get("texto")
        finally:
            arquivo.unlink(missing_ok=True)

    def _dentro_do_limite(self) -> bool:
        agora = time.time()
        while self._transcricoes and agora - self._transcricoes[0] > 60:
            self._transcricoes.popleft()
        if len(self._transcricoes) >= MAX_POR_MINUTO:
            return False
        self._transcricoes.append(agora)
        return True

    def conferir(self, frase: bytes, fim: float = 0.0) -> None:
        if not self._dentro_do_limite():
            return
        resto = depois_de_jarvis(self._transcrever(frase, TOKENS_CONFERIR) or "")
        if resto is None:
            return
        if resto or len(frase) / (TAXA * 2) > 1.5:  # tem mais coisa depois do nome: a frase inteira
            resto = depois_de_jarvis(self._transcrever(frase) or "") or resto
        print(f"ouvido: chamado (\"{resto[:60]}\")", flush=True)
        if resto:
            self._ao_chamar(resto)
            return
        with self._trava:  # já espera a pergunta enquanto o cérebro abre a janela e cumprimenta
            self._pergunta_desde, self._pergunta_ate = fim, time.time() + ESPERA_PERGUNTA_S
        desde = self._ao_chamar("")
        with self._trava:
            if desde is None:
                self._pergunta_ate = 0.0
            elif self.esperando_pergunta:
                self._pergunta_desde = max(fim, desde)
                self._pergunta_ate = max(self._pergunta_ate, time.time() + ESPERA_PERGUNTA_S)
