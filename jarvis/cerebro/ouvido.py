"""Ouvido: escuta a palavra "Jarvis" o tempo todo, como uma Alexa, com o Porcupine (tudo local, nada sai da máquina).

A AccessKey gratuita do Picovoice fica fora do repositório, em `~/.config/jarvis/picovoice.key` (ou na variável
`PICOVOICE_ACCESS_KEY`). Sem ela, ou sem o `pvporcupine`, o ouvido fica desligado e o Super+J continua valendo.
"""

import os
import subprocess
import threading
from array import array
from collections.abc import Callable
from pathlib import Path

from jarvis.cerebro.escuta import _morrer_com_o_pai

ARQUIVO_CHAVE = Path.home() / ".config/jarvis/picovoice.key"
SENSIBILIDADE = 0.6
ESPERA_REINICIO_S = 3.0


def chave() -> str | None:
    valor = os.environ.get("PICOVOICE_ACCESS_KEY", "").strip()
    if not valor:
        try:
            valor = ARQUIVO_CHAVE.read_text(encoding="utf-8").strip()
        except OSError:
            return None
    return valor or None


def detector_porcupine():
    import pvporcupine

    return pvporcupine.create(access_key=chave(), keywords=["jarvis"], sensitivities=[SENSIBILIDADE])


class Ouvido:
    def __init__(self, ao_ouvir: Callable[[], None], criar_detector: Callable = detector_porcupine,
                 comando: list[str] | None = None):
        self._ao_ouvir = ao_ouvir
        self._criar_detector = criar_detector
        self._comando = comando
        self._parando = threading.Event()
        self._proc: subprocess.Popen | None = None
        self.ligado = False

    def iniciar(self) -> bool:
        if chave() is None:
            print("ouvido: desligado (falta a AccessKey do Picovoice em ~/.config/jarvis/picovoice.key)", flush=True)
            return False
        try:
            detector = self._criar_detector()
        except Exception as erro:  # pvporcupine ausente, chave inválida ou sem rede para validá-la
            print(f"ouvido: desligado ({erro!r})", flush=True)
            return False
        self.ligado = True
        # A thread dona do gravador vive tanto quanto ele: PDEATHSIG segue a thread que o criou.
        threading.Thread(target=self._laco, args=(detector,), daemon=True).start()
        print("ouvido: escutando \"Jarvis\"", flush=True)
        return True

    def parar(self) -> None:
        self._parando.set()
        if self._proc and self._proc.poll() is None:
            self._proc.kill()

    def _laco(self, detector) -> None:
        tamanho = detector.frame_length * 2  # s16 mono
        comando = self._comando or ["pw-record", "--rate", str(detector.sample_rate), "--channels", "1",
                                    "--format", "s16", "-"]
        try:
            while not self._parando.is_set():
                try:
                    self._proc = subprocess.Popen(comando, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                                  preexec_fn=_morrer_com_o_pai)
                except OSError as erro:
                    print(f"ouvido: não abriu o microfone: {erro}", flush=True)
                    self._parando.wait(ESPERA_REINICIO_S)
                    continue
                while not self._parando.is_set():
                    bloco = self._proc.stdout.read(tamanho)
                    if len(bloco) < tamanho:  # gravador caiu: abre de novo
                        break
                    if detector.process(array("h", bloco)) >= 0:
                        threading.Thread(target=self._ao_ouvir, daemon=True).start()
                if self._proc.poll() is None:
                    self._proc.kill()
                self._proc.wait()
                self._parando.wait(ESPERA_REINICIO_S)
        finally:
            self.ligado = False
            detector.delete()
