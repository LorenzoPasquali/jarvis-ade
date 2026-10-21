"""Consultas que o Jarvis usa nas respostas: estado das sessões, histórico e clima."""

import json
import re
import subprocess
import urllib.request
from collections import Counter
from datetime import datetime, timedelta

from jarvis.orca import Agente, Terminal

ESTADOS = {
    "working": "trabalhando",
    "done": "concluiu",
    "waiting": "aguardando resposta",
    "permission": "pedindo permissão",
    "blocked": "travado",
    "idle": "ocioso",
}

_WMO = {
    0: "céu limpo", 1: "predominantemente limpo", 2: "parcialmente nublado", 3: "nublado",
    45: "neblina", 48: "neblina", 51: "garoa fraca", 53: "garoa", 55: "garoa forte",
    56: "garoa congelante", 57: "garoa congelante", 61: "chuva fraca", 63: "chuva moderada",
    65: "chuva forte", 66: "chuva congelante", 67: "chuva congelante", 71: "neve fraca",
    73: "neve", 75: "neve forte", 77: "granizo fino", 80: "pancadas de chuva fracas",
    81: "pancadas de chuva", 82: "pancadas de chuva fortes", 85: "pancadas de neve",
    86: "pancadas de neve", 95: "trovoadas", 96: "trovoadas com granizo", 99: "trovoadas com granizo",
}

URL_CLIMA = (
    "https://api.open-meteo.com/v1/forecast?latitude={latitude:.4f}&longitude={longitude:.4f}"
    "&current=temperature_2m,apparent_temperature,weather_code"
    "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
    "&timezone=auto&forecast_days=1"
)


def _ha(desde_ms: int | None, agora_ms: int) -> str:
    if desde_ms is None:
        return ""
    minutos = max(0, (agora_ms - desde_ms) // 60_000)
    return f" há {minutos} min" if minutos < 60 else f" há {minutos // 60} h"


def formatar_status(agentes: list[Agente], terminais: dict[str, Terminal], excluir_pane: str | None,
                    agora_ms: int) -> str:
    linhas = []
    for a in agentes:
        if a.pane_key == excluir_pane:
            continue
        nome = a.projeto if a.worktree in ("", a.projeto) else f"{a.projeto} ({a.worktree})"
        estado = ESTADOS.get(a.estado, a.estado)
        linha = f"• {nome} [{a.agente}] {estado}{_ha(a.estado_desde_ms, agora_ms)}"
        mensagem = " ".join(a.ultima_mensagem.split())[:160]
        if mensagem:
            linha += f" — «{mensagem}»"
        terminal = terminais.get(a.pane_key)
        linha += f" — terminal {terminal.handle}" if terminal else " — sem terminal"
        linhas.append(linha)
    return "\n".join(linhas) or "Nenhuma outra sessão de agente aberta no Orca."


def parse_periodo(texto: str, agora: datetime) -> datetime:
    m = re.fullmatch(r"(\d+)([dh])", texto.strip())
    if m:
        n = int(m.group(1))
        return agora - (timedelta(days=n) if m.group(2) == "d" else timedelta(hours=n))
    try:
        desde = datetime.fromisoformat(texto.strip())
    except ValueError:
        raise ValueError(f"Período inválido: {texto!r}. Use 1d, 7d, 12h ou uma data ISO.") from None
    return desde if desde.tzinfo else desde.astimezone()


def commits(caminho: str, desde: datetime, runner=subprocess.run) -> list[str]:
    try:
        proc = runner(["git", "-C", caminho, "log", f"--since={desde.isoformat()}", "--no-merges",
                       "--pretty=%h %ad %s", "--date=short", "-n", "20"],
                      capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    return [linha for linha in proc.stdout.splitlines() if linha.strip()]


def formatar_historico(eventos: list[dict], commits_por_projeto: dict[str, list[str]], desde: datetime) -> str:
    contagem: dict[str, Counter] = {}
    for e in eventos:
        if e.get("projeto"):
            contagem.setdefault(e["projeto"], Counter())[e["tipo"]] += 1
    projetos = sorted(set(contagem) | {p for p, c in commits_por_projeto.items() if c})
    if not projetos:
        return f"Nada registrado nos projetos desde {desde.astimezone():%d/%m %H:%M}."
    blocos = [f"Desde {desde.astimezone():%d/%m %H:%M}:"]
    for projeto in projetos:
        bloco = [projeto]
        if projeto in contagem:
            bloco.append("  eventos — " + ", ".join(f"{t}: {n}" for t, n in sorted(contagem[projeto].items())))
        if commits_por_projeto.get(projeto):
            bloco.append("  commits:")
            bloco += [f"    {c}" for c in commits_por_projeto[projeto]]
        blocos.append("\n".join(bloco))
    return "\n\n".join(blocos)


def descrever_clima(dados: dict, cidade: str) -> str:
    atual, dia = dados["current"], dados["daily"]
    ceu = _WMO.get(atual["weather_code"], "tempo indefinido")
    return (f"{cidade} agora: {round(atual['temperature_2m'])} °C "
            f"(sensação {round(atual['apparent_temperature'])} °C), {ceu}. "
            f"Hoje: mínima {round(dia['temperature_2m_min'][0])} °C, máxima {round(dia['temperature_2m_max'][0])} °C, "
            f"chance de chuva {dia['precipitation_probability_max'][0]}%.")


def clima_curto(dados: dict, cidade: str) -> str:
    atual = dados["current"]
    return f"{round(atual['temperature_2m'])} °C, {_WMO.get(atual['weather_code'], 'tempo indefinido')} em {cidade}"


def buscar_clima(latitude: float, longitude: float, timeout: float = 10.0) -> dict:
    url = URL_CLIMA.format(latitude=latitude, longitude=longitude)
    with urllib.request.urlopen(url, timeout=timeout) as resposta:
        return json.load(resposta)
