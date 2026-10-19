"""Eventos do vigia que merecem um turno do Claude, lidos com cursor próprio do cérebro."""

from pathlib import Path

from jarvis import eventos

TIPOS_PARA_CLAUDE = ("terminou", "aguardando", "permissao", "travou", "orca_indisponivel")
PRIMEIRA_LEITURA_MAXIMO = 10


class FilaEventos:
    def __init__(self, cursor: Path):
        self._cursor = cursor
        self._fila: list[dict] = []

    def _ler_cursor(self) -> int | None:
        try:
            return int(self._cursor.read_text())
        except (FileNotFoundError, ValueError):
            return None

    def coletar(self) -> list[dict]:
        offset = self._ler_cursor()
        novos, fim = eventos.ler_desde(offset or 0)
        self._cursor.write_text(str(fim))
        relevantes = [e for e in novos if e["tipo"] in TIPOS_PARA_CLAUDE]
        if offset is None:
            # primeira vez: só os mais recentes, sem despejar o histórico inteiro no Claude
            relevantes = relevantes[-PRIMEIRA_LEITURA_MAXIMO:]
        self._fila.extend(relevantes)
        return relevantes

    def retirar(self) -> list[str]:
        linhas = [eventos.formatar(e) for e in self._fila]
        self._fila.clear()
        return linhas

    @property
    def vazia(self) -> bool:
        return not self._fila
