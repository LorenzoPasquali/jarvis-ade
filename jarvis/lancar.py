"""`jarvis lancar`: dá uma tarefa ao agente de um projeto — reaproveita a sessão parada ou abre uma nova."""

import json
from datetime import datetime
from pathlib import Path

from jarvis import orca
from jarvis.config import dados
from jarvis.consultas import ESTADOS
from jarvis.orca import Agente

PARADOS = ("done", "waiting", "idle")


def _repo_do_projeto(projeto: str, repos: list[dict]) -> dict:
    nome = projeto.casefold()
    exatos = [r for r in repos if nome in ((r.get("displayName") or "").casefold(), Path(r["path"]).name.casefold())]
    candidatos = exatos or [r for r in repos if nome in (r.get("displayName") or Path(r["path"]).name).casefold()]
    if not candidatos:
        raise ValueError(f"Não achei o projeto {projeto!r} entre os projetos do Orca.")
    if len(candidatos) > 1:
        opcoes = ", ".join(r.get("displayName") or r["path"] for r in candidatos)
        raise ValueError(f"Mais de um projeto para {projeto!r}: {opcoes}.")
    return candidatos[0]


def planejar(projeto: str, tarefa: str, agentes: list[Agente], repos: list[dict]) -> dict:
    repo = _repo_do_projeto(projeto, repos)
    nome = repo.get("displayName") or Path(repo["path"]).name
    sessoes = [a for a in agentes if a.caminho == repo["path"] or a.projeto == nome]
    paradas = [a for a in sessoes if a.estado in PARADOS]
    if len(paradas) > 1:
        opcoes = ", ".join(f"{a.worktree} ({ESTADOS.get(a.estado, a.estado)})" for a in paradas)
        raise ValueError(f"Há mais de uma sessão parada em {nome}: {opcoes}. Diga em qual.")
    if paradas:
        parada = paradas[0]
        return {"acao": "enviar", "pane_key": parada.pane_key, "projeto": nome, "worktree": parada.worktree,
                "tarefa": tarefa}
    if sessoes:
        rotulo = ESTADOS.get(sessoes[0].estado, sessoes[0].estado)
        return {"acao": "perguntar",
                "motivo": f"A sessão de {nome} está {rotulo}. Espero terminar, mando mesmo assim ou abro outro agente?"}
    return {"acao": "abrir", "caminho": repo["path"], "tarefa": tarefa}


def _registrar(dados_acao: dict, resultado: str) -> None:
    linha = {"em": datetime.now().astimezone().isoformat(timespec="seconds"), "tipo": "lancar", **dados_acao,
             "resultado": resultado}
    with (dados() / "acoes.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(linha, ensure_ascii=False) + "\n")


def executar_lancamento(dados_acao: dict, executar=orca.executar) -> str:
    args = ["agent", "launch", "--agent", "claude", "--worktree", f"path:{dados_acao['caminho']}",
            "--prompt", dados_acao["tarefa"]]
    try:
        executar(args, timeout=30.0)
    except orca.OrcaErro as erro:
        _registrar(dados_acao, f"erro: {erro.codigo}")
        raise
    _registrar(dados_acao, "ok")
    return f"Agente aberto em {dados_acao['caminho']}."


def executar_plano(plano: dict, origem: str) -> str:
    if plano["acao"] == "abrir":
        return executar_lancamento({**plano, "origem": origem})
    if plano["acao"] == "enviar":
        from jarvis import enviar

        terminal = orca.terminais().get(plano["pane_key"])
        if terminal is None:
            raise ValueError(f"A sessão de {plano['projeto']} não tem mais terminal.")
        destino = enviar.Destino(terminal.handle, plano["pane_key"], plano["projeto"], terminal.caminho)
        enviar.enviar(destino, texto=plano["tarefa"], tecla=None, origem=origem, motivo="jarvis lancar",
                      confirmado=origem == "voz")
        return f"Tarefa entregue ao agente de {plano['projeto']}."
    raise ValueError(plano.get("motivo") or "Nada a executar.")
