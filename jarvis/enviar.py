"""Envio de mensagens/teclas a um agente do Orca, sempre registrado em `dados/acoes.jsonl`."""

import json
import re
from dataclasses import dataclass
from datetime import datetime

from jarvis import orca
from jarvis.config import dados
from jarvis.orca import Agente, OrcaErro, Terminal

ORIGENS = ("voz", "texto", "regra")
_TECLA_VALIDA = re.compile(r"[0-9A-Za-z]{1,2}")
_ESTADOS_COM_PERGUNTA = ("permission", "waiting")


class EnvioRecusado(Exception):
    pass


@dataclass(frozen=True)
class Destino:
    terminal: str
    pane_key: str | None
    projeto: str
    caminho: str


def _e_jarvis(pane_key: str | None, terminal: str, sessao: dict | None) -> bool:
    if not sessao:
        return False
    return (pane_key is not None and pane_key == sessao.get("pane_key")) or terminal == sessao.get("terminal")


def resolver_destino(projeto: str | None, terminal: str | None, agentes: list[Agente],
                     terminais: dict[str, Terminal], sessao: dict | None) -> Destino:
    if terminal:
        alvo = next((t for t in terminais.values() if t.handle == terminal), None)
        if alvo is None:
            raise EnvioRecusado(f"Não encontrei o terminal {terminal} no Orca.")
        if _e_jarvis(alvo.pane_key, alvo.handle, sessao):
            raise EnvioRecusado("Esse terminal é a própria sessão do Jarvis.")
        if not alvo.gravavel:
            raise EnvioRecusado(f"O terminal {terminal} não aceita entrada agora.")
        dono = next((a for a in agentes if a.pane_key == alvo.pane_key), None)
        if dono is None:
            raise EnvioRecusado(f"O terminal {terminal} não tem um agente; o Jarvis só envia para sessões de agentes.")
        return Destino(alvo.handle, alvo.pane_key, dono.projeto, alvo.caminho)

    if not projeto:
        raise EnvioRecusado("Informe --projeto ou --terminal.")
    nome = projeto.casefold()
    candidatos = [a for a in agentes if nome in (a.projeto.casefold(), a.worktree.casefold())]
    if any(_e_jarvis(a.pane_key, "", sessao) for a in candidatos):
        raise EnvioRecusado("Esse destino é a própria sessão do Jarvis.")
    if not candidatos:
        raise EnvioRecusado(f"Nenhuma sessão de agente aberta para {projeto!r}.")
    com_terminal = [(a, terminais.get(a.pane_key)) for a in candidatos]
    if len(com_terminal) > 1:
        opcoes = "; ".join(f"{a.projeto}/{a.worktree} → {t.handle if t else 'sem terminal'}" for a, t in com_terminal)
        raise EnvioRecusado(f"Mais de uma sessão para {projeto!r}: {opcoes}. Use --terminal.")
    agente, alvo = com_terminal[0]
    if alvo is None or not alvo.gravavel:
        raise EnvioRecusado(f"A sessão de {agente.projeto} não tem terminal que aceite entrada.")
    return Destino(alvo.handle, agente.pane_key, agente.projeto, agente.caminho)


def _registrar(destino: Destino, texto: str | None, tecla: str | None, origem: str, motivo: str,
               confirmado: bool, resultado: str) -> None:
    acao = {"em": datetime.now().astimezone().isoformat(timespec="seconds"), "terminal": destino.terminal,
            "pane_key": destino.pane_key, "projeto": destino.projeto, "texto": texto, "tecla": tecla,
            "origem": origem, "motivo": motivo, "confirmado": confirmado, "resultado": resultado}
    with (dados() / "acoes.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(acao, ensure_ascii=False) + "\n")


def _validar(texto: str | None, tecla: str | None, origem: str, motivo: str, confirmado: bool) -> str | None:
    if (texto is None) == (tecla is None) or (texto is not None and not texto.strip()):
        return "informe exatamente um entre texto e tecla"
    if texto is not None and texto.lstrip()[0] in "!/":
        return "texto começando com ! ou / vira comando no agente e não é permitido"
    if tecla is not None and not _TECLA_VALIDA.fullmatch(tecla):
        return "tecla deve ser uma opção curta, como 1 ou y"
    if origem not in ORIGENS:
        return f"origem inválida: {origem}"
    if origem == "voz" and not confirmado:
        return "ordem falada sem confirmação do usuário"
    if origem == "regra" and not motivo.strip():
        return "envio por regra sem a regra no motivo"
    return None


def _estado_no_orca(pane_key: str | None) -> str | None:
    return next((a.estado for a in orca.agentes() if a.pane_key == pane_key), None)


def _validar_estado(estado: str | None, texto: str | None) -> str | None:
    if estado is None:
        return "a sessão do agente não está mais aberta"
    if texto is not None and estado == "permission":
        return "o agente está num pedido de permissão; Enter aprovaria a opção marcada (responda com --tecla)"
    if texto is None and estado not in _ESTADOS_COM_PERGUNTA:
        return "não há pergunta ou pedido de permissão aberto nesse agente"
    return None


def enviar(destino: Destino, *, texto: str | None, tecla: str | None, origem: str, motivo: str,
           confirmado: bool, executar=None, estado_atual=None) -> dict:
    executar = executar or orca.executar
    estado_atual = estado_atual or _estado_no_orca
    problema = _validar(texto, tecla, origem, motivo, confirmado) or _validar_estado(estado_atual(destino.pane_key),
                                                                                      texto)
    if problema:
        _registrar(destino, texto, tecla, origem, motivo, confirmado, f"recusado: {problema}")
        raise EnvioRecusado(f"Não enviei: {problema}.")
    args = ["terminal", "send", "--terminal", destino.terminal, "--text"]
    args += [texto, "--enter"] if texto is not None else [tecla]
    try:
        resultado = executar(args)
    except OrcaErro as erro:
        _registrar(destino, texto, tecla, origem, motivo, confirmado, f"erro: {erro.codigo}")
        raise
    _registrar(destino, texto, tecla, origem, motivo, confirmado, "ok")
    return resultado
