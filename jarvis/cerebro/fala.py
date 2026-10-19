"""Separa, durante o streaming, as linhas 🔊 da resposta para a voz começar antes do fim."""

from collections.abc import Callable

from jarvis.texto_fala import MARCADOR, SILENCIO, extrair_fala


class SeparadorFala:
    def __init__(self, falar: Callable[[str], None]):
        self._falar = falar
        self.reiniciar()

    def reiniciar(self) -> None:
        self._buffer = ""
        self._marcou = False

    def alimentar(self, delta: str) -> None:
        self._buffer += delta
        while "\n" in self._buffer:
            linha, self._buffer = self._buffer.split("\n", 1)
            self._linha(linha)

    def fim(self, texto_completo: str) -> None:
        if self._buffer:
            self._linha(self._buffer)
        if not self._marcou:
            fala = extrair_fala(texto_completo)
            if fala:
                self._falar(fala)
        self.reiniciar()

    def _linha(self, linha: str) -> None:
        limpa = linha.strip()
        if limpa.startswith(SILENCIO):
            self._marcou = True
        elif limpa.startswith(MARCADOR):
            self._marcou = True
            fala = extrair_fala(limpa)
            if fala:
                self._falar(fala)
