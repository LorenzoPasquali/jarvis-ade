"""Compara snapshots das sessões do Orca e registra as transições como eventos."""

import json
import sys
import time
import uuid
from dataclasses import asdict
from datetime import datetime
from typing import NoReturn

from jarvis import eventos, orca, sessao
from jarvis.config import dados
from jarvis.orca import Agente, OrcaErro

_TIPO_POR_ESTADO = {"done": "terminou", "waiting": "aguardando", "permission": "permissao", "blocked": "travou"}
# "done" oscila entre turnos; só anuncia "terminou" se continuar assim por este tempo.
ESPERA_TERMINOU_S = 15


def _agora() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _evento(tipo: str, agora_iso: str, agente: Agente | None = None) -> dict:
    base = {"id": uuid.uuid4().hex, "em": agora_iso, "tipo": tipo, "projeto": "", "worktree": "",
            "caminho": "", "pane_key": "", "agente": "", "estado": "", "resumo": ""}
    if agente:
        base.update(projeto=agente.projeto, worktree=agente.worktree, caminho=agente.caminho,
                    pane_key=agente.pane_key, agente=agente.agente, estado=agente.estado,
                    resumo=agente.ultima_mensagem[:300])
    return base


def diferenca(antes: dict[str, Agente], depois: dict[str, Agente], agora_iso: str) -> list[dict]:
    novos = []
    for pane, atual in depois.items():
        anterior = antes.get(pane)
        if anterior is None:
            novos.append(_evento("sessao_aberta", agora_iso, atual))
        elif atual.estado != anterior.estado and atual.estado in _TIPO_POR_ESTADO:
            novos.append(_evento(_TIPO_POR_ESTADO[atual.estado], agora_iso, atual))
    for pane, anterior in antes.items():
        if pane not in depois:
            novos.append(_evento("sessao_fechada", agora_iso, anterior))
    return novos


def _arquivo_estado():
    return dados() / "vigia-estado.json"


def _ler_estado() -> dict | None:
    try:
        bruto = json.loads(_arquivo_estado().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return {"agentes": {p: Agente(**a) for p, a in bruto.get("agentes", {}).items()},
            "orca_ok": bruto.get("orca_ok", True), "adiados": bruto.get("adiados", {})}


def _salvar_estado(agentes: dict[str, Agente], orca_ok: bool, adiados: dict[str, dict]) -> None:
    bruto = {"agentes": {p: asdict(a) for p, a in agentes.items()}, "orca_ok": orca_ok, "adiados": adiados}
    _arquivo_estado().write_text(json.dumps(bruto, ensure_ascii=False), encoding="utf-8")


def _confirmar_terminados(adiados: dict[str, dict], depois: dict[str, Agente], agora_iso: str) -> list[dict]:
    """Remove de `adiados` (in place) e devolve os "terminou" que já ficaram estáveis."""
    agora = datetime.fromisoformat(agora_iso)
    confirmados = []
    for pane, e in list(adiados.items()):
        atual = depois.get(pane)
        if atual is None or atual.estado != "done":
            del adiados[pane]
        elif (agora - datetime.fromisoformat(e["em"])).total_seconds() >= ESPERA_TERMINOU_S:
            confirmados.append({**e, "em": agora_iso, "resumo": atual.ultima_mensagem[:300]})
            del adiados[pane]
    return confirmados


def passo(obter=orca.agentes, agora_iso: str | None = None) -> list[dict]:
    agora_iso = agora_iso or _agora()
    estado = _ler_estado()
    jarvis = (sessao.ler() or {}).get("pane_key")
    try:
        depois = {a.pane_key: a for a in obter() if a.pane_key != jarvis}
    except OrcaErro:
        if estado is None:
            return []
        novos = [_evento("orca_indisponivel", agora_iso)] if estado["orca_ok"] else []
        _salvar_estado(estado["agentes"], orca_ok=False, adiados=estado["adiados"])
        for e in novos:
            eventos.anexar(e)
        return novos
    if estado is None:
        _salvar_estado(depois, orca_ok=True, adiados={})
        return []
    antes = {p: a for p, a in estado["agentes"].items() if p != jarvis}
    novos = [] if estado["orca_ok"] else [_evento("orca_disponivel", agora_iso)]
    adiados = estado["adiados"]
    for e in diferenca(antes, depois, agora_iso):
        if e["tipo"] == "terminou":
            adiados[e["pane_key"]] = e
        else:
            novos.append(e)
    novos += _confirmar_terminados(adiados, depois, agora_iso)
    _salvar_estado(depois, orca_ok=True, adiados=adiados)
    for e in novos:
        eventos.anexar(e)
    return novos


def rodar(intervalo: float = 5.0) -> NoReturn:
    while True:
        try:
            passo()
        except Exception as erro:  # o vigia não pode morrer por um erro isolado
            print(f"vigia: {erro!r}", file=sys.stderr, flush=True)
        time.sleep(intervalo)
