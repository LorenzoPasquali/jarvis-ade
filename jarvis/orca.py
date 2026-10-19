"""Chamadas à CLI documentada do Orca (`orca ... --json`) e leitura do resultado."""

import json
import subprocess
from dataclasses import dataclass

_MENSAGENS = {
    "cli_indisponivel": "Não encontrei o comando orca neste ambiente.",
    "timeout": "O Orca demorou demais para responder.",
    "resposta_invalida": "O Orca respondeu num formato que não reconheço.",
    "runtime_unavailable": "Não consegui falar com o Orca. Ele está aberto?",
}


class OrcaErro(Exception):
    def __init__(self, codigo: str, mensagem: str):
        super().__init__(f"{mensagem} ({codigo})")
        self.codigo = codigo
        self.mensagem = mensagem


def _erro(codigo: str, detalhe: str = "") -> OrcaErro:
    return OrcaErro(codigo, _MENSAGENS.get(codigo, detalhe or "O Orca respondeu com erro."))


@dataclass(frozen=True)
class Agente:
    pane_key: str
    projeto: str
    worktree: str
    caminho: str
    agente: str
    estado: str
    ultima_mensagem: str
    prompt: str
    estado_desde_ms: int | None
    ferramenta: str | None


@dataclass(frozen=True)
class Terminal:
    handle: str
    pane_key: str
    caminho: str
    gravavel: bool


def executar(args: list[str], timeout: float = 10.0, runner=subprocess.run) -> dict:
    try:
        proc = runner(["orca", *args, "--json"], capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise _erro("cli_indisponivel") from None
    except subprocess.TimeoutExpired:
        raise _erro("timeout") from None
    try:
        resposta = json.loads(proc.stdout)
    except (json.JSONDecodeError, TypeError):
        raise _erro("resposta_invalida") from None
    if not isinstance(resposta, dict):
        raise _erro("resposta_invalida")
    if resposta.get("ok") is not True:
        erro = resposta.get("error") or {}
        raise _erro(str(erro.get("code") or "erro_orca"), str(erro.get("message") or ""))
    return resposta.get("result") or {}


def listar_agentes(resultado_ps: dict) -> list[Agente]:
    agentes = []
    for wt in resultado_ps.get("worktrees", []):
        for a in wt.get("agents") or []:
            if a.get("parentPaneKey"):
                continue
            agentes.append(Agente(
                pane_key=a["paneKey"],
                projeto=wt.get("repo") or "",
                worktree=wt.get("displayName") or "",
                caminho=wt.get("path") or "",
                agente=a.get("agentType") or "",
                estado=a.get("state") or "",
                ultima_mensagem=a.get("lastAssistantMessage") or "",
                prompt=a.get("prompt") or "",
                estado_desde_ms=a.get("stateStartedAt"),
                ferramenta=a.get("toolName"),
            ))
    return agentes


def mapa_terminais(resultado_list: dict) -> dict[str, Terminal]:
    mapa = {}
    for t in resultado_list.get("terminals", []):
        pane_key = f"{t.get('tabId')}:{t.get('leafId')}"
        mapa[pane_key] = Terminal(
            handle=t["handle"],
            pane_key=pane_key,
            caminho=t.get("worktreePath") or "",
            gravavel=bool(t.get("writable")) and bool(t.get("connected")),
        )
    return mapa


def agentes() -> list[Agente]:
    return listar_agentes(executar(["worktree", "ps"]))


def terminais() -> dict[str, Terminal]:
    return mapa_terminais(executar(["terminal", "list"]))
