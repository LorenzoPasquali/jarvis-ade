"""Todos os projetos do Orca, com a última atividade — mesmo os que não têm aba de agente aberta.

O último status de cada projeto sai do histórico que o próprio agente grava em disco: as conversas do Claude Code
(`~/.claude/projects/<pasta>/*.jsonl`) e do Codex (`~/.codex/sessions/**/rollout-*.jsonl`), mais o último commit.
"""

import json
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from jarvis import orca
from jarvis.consultas import ESTADOS
from jarvis.orca import Agente
from jarvis.config import RAIZ

CAUDA_BYTES = 600_000
DIAS_CODEX = 30
MAX_RESPOSTA = 2000
_IGNORAR_PEDIDO = ("<", "Another Claude session", "[Request interrupted", "Caveat:",
                   "This session is being continued", "Base directory for this skill")


@dataclass
class Projeto:
    nome: str
    caminho: str
    ts: float = 0.0  # última atividade (agente ou commit), em segundos
    agente: str = ""
    ts_agente: float = 0.0
    pedido: str = ""
    resposta: str = ""
    commit: str = ""
    ts_commit: float = 0.0
    sessao: str = ""  # estado da aba de agente aberta no Orca, se houver
    caminhos: list[str] = field(default_factory=list)


def _home() -> Path:
    return Path.home()


def _ts(iso: str | None) -> float:
    if not iso:
        return 0.0
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _cauda(arquivo: Path) -> list[str]:
    with arquivo.open("rb") as f:
        f.seek(0, 2)
        tamanho = f.tell()
        f.seek(max(0, tamanho - CAUDA_BYTES))
        linhas = f.read().decode("utf-8", "replace").splitlines()
    return linhas[1:] if tamanho > CAUDA_BYTES else linhas


def _pedido_util(texto: str) -> bool:
    texto = texto.strip()
    return bool(texto) and not texto.startswith(_IGNORAR_PEDIDO)


def _textos(conteudo, tipo_bloco: str) -> list[str]:
    if isinstance(conteudo, str):
        return [conteudo]
    return [b.get("text") or "" for b in conteudo or [] if isinstance(b, dict) and b.get("type") == tipo_bloco]


# ---------- Claude Code ----------

def pasta_claude(caminho: str) -> Path:
    return _home() / ".claude/projects" / re.sub(r"[^A-Za-z0-9]", "-", caminho)


def troca_claude(linhas: list[str]) -> tuple[str, str, float]:
    """Último pedido do senhor, última resposta em texto do agente e a hora dela."""
    pedido, resposta, ts = "", "", 0.0
    for linha in linhas:
        try:
            d = json.loads(linha)
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        tipo = d.get("type")
        if tipo not in ("user", "assistant") or d.get("isMeta") or d.get("isSidechain"):
            continue
        conteudo = (d.get("message") or {}).get("content")
        if tipo == "user":
            for texto in _textos(conteudo, "text"):
                if _pedido_util(texto):
                    pedido = texto.strip()
        else:
            textos = [t for t in _textos(conteudo, "text") if t.strip()]
            if textos:
                resposta, ts = textos[-1].strip(), _ts(d.get("timestamp"))
    return pedido, resposta, ts


def _ultimo_claude(caminhos: list[str]) -> tuple[Path, float] | None:
    candidatos = [(a, a.stat().st_mtime) for c in caminhos for a in pasta_claude(c).glob("*.jsonl")]
    return max(candidatos, key=lambda x: x[1]) if candidatos else None


# ---------- Codex ----------

def troca_codex(linhas: list[str]) -> tuple[str, str, float]:
    pedido, resposta, ts = "", "", 0.0
    for linha in linhas:
        try:
            d = json.loads(linha)
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        carga = d.get("payload") or {}
        if d.get("type") != "response_item" or carga.get("type") != "message":
            continue
        if carga.get("role") == "user":
            for texto in _textos(carga.get("content"), "input_text"):
                if _pedido_util(texto):
                    pedido = texto.strip()
        elif carga.get("role") == "assistant":
            textos = [t for t in _textos(carga.get("content"), "output_text") if t.strip()]
            if textos:
                resposta, ts = textos[-1].strip(), _ts(d.get("timestamp"))
    return pedido, resposta, ts


def sessoes_codex(agora: float | None = None) -> dict[str, tuple[Path, float]]:
    """Pasta de trabalho -> (conversa mais recente do Codex nela, mtime). Ignora o próprio Jarvis no modo reserva."""
    limite = (agora or time.time()) - DIAS_CODEX * 86400
    por_pasta: dict[str, tuple[Path, float]] = {}
    for arquivo in (_home() / ".codex/sessions").glob("*/*/*/rollout-*.jsonl"):
        mtime = arquivo.stat().st_mtime
        if mtime < limite:
            continue
        try:
            with arquivo.open(encoding="utf-8") as f:
                cwd = (json.loads(f.readline()).get("payload") or {}).get("cwd") or ""
        except (OSError, ValueError):
            continue
        if not cwd or cwd.startswith(str(RAIZ / "sessao")):
            continue
        if cwd not in por_pasta or mtime > por_pasta[cwd][1]:
            por_pasta[cwd] = (arquivo, mtime)
    return por_pasta


# ---------- git ----------

def ultimo_commit(caminho: str, runner=subprocess.run) -> tuple[str, float]:
    try:
        r = runner(["git", "-C", caminho, "log", "-1", "--format=%ct%x1f%s"], capture_output=True, text=True,
                   timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return "", 0.0
    if r.returncode != 0 or "\x1f" not in r.stdout:
        return "", 0.0
    ts, assunto = r.stdout.strip().split("\x1f", 1)
    return assunto, float(ts)


# ---------- juntando ----------

_cache: dict[Path, tuple[float, tuple[str, str, float]]] = {}


def _troca(arquivo: Path, mtime: float, ler) -> tuple[str, str, float]:
    guardado = _cache.get(arquivo)
    if guardado and guardado[0] == mtime:
        return guardado[1]
    try:
        troca = ler(_cauda(arquivo))
    except OSError:
        troca = ("", "", 0.0)
    _cache[arquivo] = (mtime, troca)
    return troca


def _aplicar_sessao(p: Projeto, agentes: list[Agente]) -> None:
    """Aba aberta no Orca: vale o estado dela e, se for mais nova, a última mensagem (ex.: agente na VPS)."""
    abertas = [a for a in agentes if a.projeto == p.nome or a.caminho in p.caminhos]
    if not abertas:
        return
    a = max(abertas, key=lambda a: a.estado_desde_ms or 0)
    p.sessao = a.estado
    ts = (a.estado_desde_ms or 0) / 1000
    if a.ultima_mensagem and ts >= p.ts_agente:
        p.agente, p.resposta, p.ts_agente = a.agente, a.ultima_mensagem[:MAX_RESPOSTA], ts
        p.pedido = a.prompt[:500] or p.pedido


def montar(repos: list[dict], worktrees: list[dict], codex: dict[str, tuple[Path, float]] | None = None,
           commit=ultimo_commit, agentes: list[Agente] | None = None) -> list[Projeto]:
    codex = sessoes_codex() if codex is None else codex
    projetos = []
    for r in repos:
        caminho = r.get("path") or ""
        if caminho in ("", "/"):
            continue
        nome = r.get("displayName") or Path(caminho).name
        caminhos = [caminho] + [w["path"] for w in worktrees
                                if w.get("repo") == nome and w.get("path") and w["path"] != caminho]
        p = Projeto(nome=nome, caminho=caminho, caminhos=caminhos)
        claude = _ultimo_claude(caminhos)
        do_codex = [codex[c] for c in caminhos if c in codex]
        fontes = ([("claude", *claude, troca_claude)] if claude else []) + \
                 [("codex", a, m, troca_codex) for a, m in do_codex]
        if fontes:
            agente, arquivo, mtime, ler = max(fontes, key=lambda f: f[2])
            pedido, resposta, ts = _troca(arquivo, mtime, ler)
            p.agente, p.pedido, p.resposta = agente, pedido[:500], resposta[:MAX_RESPOSTA]
            p.ts_agente = ts or mtime
        _aplicar_sessao(p, agentes or [])
        p.commit, p.ts_commit = commit(caminho)
        p.ts = max(p.ts_agente, p.ts_commit)
        projetos.append(p)
    return sorted(projetos, key=lambda p: p.ts, reverse=True)


def listar() -> list[Projeto]:
    repos = orca.executar(["repo", "list"]).get("repos", [])
    try:
        ps = orca.executar(["worktree", "ps"])
    except orca.OrcaErro:
        ps = {}
    return montar(repos, ps.get("worktrees", []), agentes=orca.listar_agentes(ps))


def encontrar(nome: str, projetos: list[Projeto]) -> Projeto:
    alvo = nome.casefold()
    exatos = [p for p in projetos if alvo in (p.nome.casefold(), Path(p.caminho).name.casefold())]
    candidatos = exatos or [p for p in projetos if alvo in p.nome.casefold() or alvo in p.caminho.casefold()]
    if not candidatos:
        raise ValueError(f"Não achei o projeto {nome!r} no Orca.")
    if len(candidatos) > 1:
        raise ValueError(f"Mais de um projeto para {nome!r}: {', '.join(p.nome for p in candidatos)}.")
    return candidatos[0]


# ---------- texto ----------

def ha(ts: float, agora: float) -> str:
    if not ts:
        return "sem atividade"
    minutos = max(0, int((agora - ts) // 60))
    if minutos < 60:
        return f"há {minutos} min"
    horas = minutos // 60
    return f"há {horas} h" if horas < 48 else f"há {horas // 24} dias"


def _linha(texto: str, limite: int) -> str:
    texto = " ".join(texto.split())
    return texto if len(texto) <= limite else texto[:limite - 1] + "…"


def formatar_lista(projetos: list[Projeto], agora: float, limite: int = 10) -> str:
    if not projetos:
        return "Nenhum projeto no Orca."
    linhas = []
    for p in projetos[:limite]:
        linha = f"• {p.nome} — {ha(p.ts, agora)}"
        if p.sessao:
            linha += f" — aba aberta: {ESTADOS.get(p.sessao, p.sessao)}"
        if p.resposta:
            linha += f" — último agente ({p.agente}, {ha(p.ts_agente, agora)}): «{_linha(p.resposta, 200)}»"
        if p.commit:
            linha += f" — último commit {ha(p.ts_commit, agora)}: {_linha(p.commit, 80)}"
        linhas.append(linha)
    if len(projetos) > limite:
        linhas.append(f"(+{len(projetos) - limite} projetos sem atividade recente: "
                      f"{', '.join(p.nome for p in projetos[limite:])})")
    return "\n".join(linhas)


def formatar_detalhe(p: Projeto, agora: float, commits: list[str] | None = None) -> str:
    linhas = [f"{p.nome} ({p.caminho}) — última atividade {ha(p.ts, agora)}"]
    if p.sessao:
        linhas.append(f"Aba de agente aberta no Orca: {ESTADOS.get(p.sessao, p.sessao)}.")
    if p.agente:
        linhas.append(f"Último agente: {p.agente}, {ha(p.ts_agente, agora)}.")
        if p.pedido:
            linhas.append(f"Último pedido do senhor: «{_linha(p.pedido, 400)}»")
        if p.resposta:
            linhas.append(f"Última resposta do agente:\n{p.resposta}")
    else:
        linhas.append("Nenhuma conversa de agente registrada para este projeto.")
    if commits:
        linhas.append("Últimos commits:\n" + "\n".join(f"- {c}" for c in commits))
    return "\n".join(linhas)


def commits_recentes(caminho: str, n: int = 5, runner=subprocess.run) -> list[str]:
    try:
        r = runner(["git", "-C", caminho, "log", f"-{n}", "--format=%cr — %s"], capture_output=True, text=True,
                   timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return r.stdout.splitlines() if r.returncode == 0 else []


def como_dict(p: Projeto) -> dict:
    return asdict(p)
