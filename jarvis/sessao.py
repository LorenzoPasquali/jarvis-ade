"""Registro da sessão Jarvis (pane e terminal do Orca) feito pelo lançador."""

import json
from datetime import datetime

from jarvis.config import dados


def _arquivo():
    return dados() / "sessao.json"


def registrar(pane_key: str, terminal: str) -> None:
    registro = {"pane_key": pane_key, "terminal": terminal,
                "iniciada_em": datetime.now().astimezone().isoformat(timespec="seconds")}
    _arquivo().write_text(json.dumps(registro, ensure_ascii=False), encoding="utf-8")


def ler() -> dict | None:
    try:
        return json.loads(_arquivo().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
