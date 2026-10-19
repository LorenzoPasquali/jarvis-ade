"""Ações que só acontecem com a aprovação do senhor: botão na janela ou "sim" seguido de `jarvis confirmar`.

Ficam em `dados/pendencias.json`; expiram em 10 min sem executar.
"""

import fcntl
import json
import time
from contextlib import contextmanager
from datetime import datetime

from jarvis.config import RAIZ, dados

ARQUIVO_REGRAS = RAIZ / "sessao/regras.md"
EXPIRA_S = 600
TIPOS = ("enviar", "regra", "lancar")


@contextmanager
def _travado():
    """CLI (chamado pelo Claude) e cérebro mexem no mesmo arquivo: uma trava por vez."""
    with (dados() / "pendencias.lock").open("w") as trava:
        fcntl.flock(trava, fcntl.LOCK_EX)
        yield


def _arquivo():
    return dados() / "pendencias.json"


def _carregar() -> list[dict]:
    try:
        itens = json.loads(_arquivo().read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return []
    agora = time.time()
    for p in itens:
        if p["estado"] == "aguardando" and agora - p["criada_ts"] > EXPIRA_S:
            p["estado"] = "expirada"
    return itens


def _salvar(itens: list[dict]) -> None:
    _arquivo().write_text(json.dumps(itens, ensure_ascii=False, indent=1), encoding="utf-8")


def criar(tipo: str, descricao: str, dados_acao: dict) -> dict:
    if tipo not in TIPOS:
        raise ValueError(f"Tipo de pendência desconhecido: {tipo}")
    with _travado():
        itens = _carregar()
        pendencia = {"id": max((p["id"] for p in itens), default=0) + 1, "tipo": tipo, "descricao": descricao,
                     "dados": dados_acao, "estado": "aguardando", "resultado": "", "criada_ts": time.time(),
                     "criada_em": datetime.now().astimezone().isoformat(timespec="seconds")}
        itens.append(pendencia)
        _salvar(itens[-100:])
    return pendencia


def listar(apenas_abertas: bool = True) -> list[dict]:
    with _travado():
        itens = _carregar()
        _salvar(itens)
    return [p for p in itens if p["estado"] == "aguardando"] if apenas_abertas else itens


def obter(id_: int) -> dict:
    with _travado():
        itens = _carregar()
    pendencia = next((p for p in itens if p["id"] == id_), None)
    if pendencia is None:
        raise ValueError(f"Não existe a pendência {id_}.")
    return pendencia


def _aberta(itens: list[dict], id_: int) -> dict:
    pendencia = next((p for p in itens if p["id"] == id_), None)
    if pendencia is None:
        raise ValueError(f"Não existe a pendência {id_}.")
    if pendencia["estado"] != "aguardando":
        raise ValueError(f"A pendência {id_} não está aberta ({pendencia['estado']}).")
    return pendencia


def _adicionar_regra(texto: str) -> str:
    conteudo = ARQUIVO_REGRAS.read_text(encoding="utf-8").replace("\n(nenhuma)\n", "\n")
    ARQUIVO_REGRAS.write_text(conteudo.rstrip("\n") + f"\n- {texto.strip()}\n", encoding="utf-8")
    return f"Regra registrada: {texto.strip()}"


def remover_regra(numero: int) -> str:
    linhas = ARQUIVO_REGRAS.read_text(encoding="utf-8").splitlines()
    regras = [i for i, linha in enumerate(linhas) if linha.startswith("- ")]
    if not 1 <= numero <= len(regras):
        raise ValueError(f"Não existe a regra {numero}.")
    removida = linhas.pop(regras[numero - 1])
    if len(regras) == 1:
        linhas.append("(nenhuma)")
    ARQUIVO_REGRAS.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return f"Regra removida: {removida[2:]}"


def _executar(pendencia: dict) -> str:
    acao = pendencia["dados"]
    if pendencia["tipo"] == "regra":
        return _adicionar_regra(acao["texto"])
    if pendencia["tipo"] == "enviar":
        from jarvis import enviar

        destino = enviar.Destino(acao["terminal"], acao.get("pane_key"), acao.get("projeto", ""),
                                 acao.get("caminho", ""))
        enviar.enviar(destino, texto=acao["texto"], tecla=None, origem="voz", motivo="confirmado pelo senhor",
                      confirmado=True)
        return f"Enviado para {destino.projeto or destino.caminho}."
    from jarvis import lancar

    return lancar.executar_plano(acao, origem="voz")


def confirmar(id_: int) -> dict:
    with _travado():
        itens = _carregar()
        pendencia = _aberta(itens, id_)
        try:
            pendencia["resultado"] = _executar(pendencia)
            pendencia["estado"] = "executada"
        except Exception as erro:  # registra a falha na própria pendência; quem chamou decide o que dizer
            pendencia["resultado"] = str(erro)
            pendencia["estado"] = "falhou"
        _salvar(itens)
    return pendencia


def recusar(id_: int) -> dict:
    with _travado():
        itens = _carregar()
        pendencia = _aberta(itens, id_)
        pendencia["estado"] = "recusada"
        _salvar(itens)
    return pendencia
