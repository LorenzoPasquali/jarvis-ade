"""Que tipo de turno o cérebro está rodando agora — e o que o Claude pode fazer nele.

O cérebro grava `dados/turno.json` ao mandar cada mensagem ao Claude headless e o encerra no fim do turno.
Os comandos `jarvis enviar/lancar/confirmar` chamados de dentro do cérebro (`JARVIS_CEREBRO=1`) só valem no
tipo de turno certo: assim, um texto vindo de um agente ou da web num turno de eventos não consegue mandar,
abrir agente ou confirmar nada em nome do senhor. Fora do cérebro (o senhor no terminal) não há restrição.
"""

import json
import os
import time
import uuid

from jarvis.config import dados

TIPOS = ("texto", "voz", "eventos", "sistema")

# (ação, origem) -> tipos de turno em que vale
PERMITIDO = {
    ("enviar", "texto"): {"texto"},
    ("enviar", "voz"): {"voz"},
    ("enviar", "regra"): {"eventos"},
    ("lancar", "texto"): {"texto"},
    ("lancar", "voz"): {"voz"},
}


class ForaDoTurno(Exception):
    pass


def _arquivo():
    return dados() / "turno.json"


def registrar(tipo: str) -> dict:
    if tipo not in TIPOS:
        raise ValueError(f"tipo de turno desconhecido: {tipo}")
    turno = {"id": uuid.uuid4().hex, "tipo": tipo, "inicio": time.time()}
    _arquivo().write_text(json.dumps(turno))
    return turno


def encerrar() -> None:
    _arquivo().write_text(json.dumps({"id": None, "tipo": None, "inicio": time.time()}))


def atual() -> dict:
    try:
        return json.loads(_arquivo().read_text())
    except (FileNotFoundError, ValueError):
        return {"id": None, "tipo": None, "inicio": 0.0}


def _no_cerebro() -> bool:
    return os.environ.get("JARVIS_CEREBRO") == "1"


def exigir(acao: str, origem: str) -> None:
    if not _no_cerebro():
        return
    tipo = atual()["tipo"]
    if tipo not in PERMITIDO.get((acao, origem), set()):
        raise ForaDoTurno(f"Recusado: `{acao} --origem {origem}` não vale num turno de {tipo or 'nenhum'}. "
                          "Só o senhor pode pedir isso.")


def exigir_confirmacao(pendencia: dict) -> None:
    """`jarvis confirmar` só depois de o senhor falar, num turno de voz posterior à pendência."""
    if not _no_cerebro():
        return
    turno = atual()
    if turno["tipo"] != "voz" or turno["inicio"] <= pendencia["criada_ts"]:
        raise ForaDoTurno("Recusado: só confirmo uma pendência depois de o senhor dizer \"sim\" "
                          "(ou pelo botão na janela).")
