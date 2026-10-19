"""Log de eventos do vigia (`dados/eventos.jsonl`) e leitura com cursor."""

import json
import re
import time
from collections.abc import Iterator

from jarvis.config import dados

_DESCRICAO = {
    "terminou": "terminou",
    "aguardando": "aguardando resposta",
    "permissao": "pedindo permissão",
    "travou": "travou",
    "sessao_aberta": "nova sessão aberta",
    "sessao_fechada": "sessão fechada",
    "orca_indisponivel": "Orca fora do ar",
    "orca_disponivel": "Orca de volta",
}


def _log():
    return dados() / "eventos.jsonl"


def _cursor():
    return dados() / "eventos-cursor"


def anexar(evento: dict) -> None:
    with _log().open("a", encoding="utf-8") as f:
        f.write(json.dumps(evento, ensure_ascii=False) + "\n")


def ler_desde(offset: int) -> tuple[list[dict], int]:
    """Eventos completos a partir de `offset` (bytes) e o novo offset."""
    try:
        with _log().open("rb") as f:
            if offset > f.seek(0, 2):
                offset = 0
            f.seek(offset)
            bruto = f.read()
    except FileNotFoundError:
        return [], 0
    fim = bruto.rfind(b"\n") + 1
    lidos = [json.loads(linha) for linha in bruto[:fim].splitlines() if linha.strip()]
    return lidos, offset + fim


def _ler_cursor() -> int:
    try:
        return int(_cursor().read_text())
    except (FileNotFoundError, ValueError):
        return 0


def _gravar_cursor(offset: int) -> None:
    _cursor().write_text(str(offset))


def formatar(evento: dict) -> str:
    descricao = _DESCRICAO.get(evento["tipo"], evento["tipo"])
    projeto = evento.get("projeto") or ""
    if not projeto:
        return f"[evento] {descricao}"
    worktree = evento.get("worktree") or ""
    alvo = projeto if worktree in ("", projeto) else f"{projeto} ({worktree})"
    linha = f"[evento] {alvo}: {descricao}"
    resumo = " ".join(re.sub(r"[«»\x00-\x1f\x7f]", " ", evento.get("resumo") or "").split())
    return f"{linha} — «{resumo}»" if resumo else linha


def pendentes(maximo: int = 30) -> str:
    lidos, offset = ler_desde(_ler_cursor())
    _gravar_cursor(offset)
    if not lidos:
        return "Nenhum evento novo."
    linhas = [formatar(e) for e in lidos[-maximo:]]
    if len(lidos) > maximo:
        linhas.insert(0, f"… e mais {len(lidos) - maximo} eventos anteriores")
    return "\n".join(linhas)


def seguir(intervalo: float = 0.5, atraso_maximo: int = 10) -> Iterator[str]:
    """Começa no cursor (o que `pendentes` ainda não mostrou) e rende cada evento novo.

    Ao rearmar o monitor nada se perde; um atraso grande vira uma linha de resumo.
    """
    offset = _ler_cursor()

    def gerar() -> Iterator[str]:
        nonlocal offset
        primeira = True
        while True:
            lidos, novo = ler_desde(offset)
            _gravar_cursor(novo)
            if primeira and len(lidos) > atraso_maximo:
                yield f"[evento] … e mais {len(lidos) - atraso_maximo} eventos anteriores (veja jarvis historico)"
                lidos = lidos[-atraso_maximo:]
            primeira = False
            for e in lidos:
                yield formatar(e)
            offset = novo
            if not lidos:
                time.sleep(intervalo)

    return gerar()
