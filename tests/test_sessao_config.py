import json
import os
from pathlib import Path

import pytest

from conftest import RAIZ
from jarvis import lancador, sessao
from jarvis.lancador import iniciar


def test_persona_tem_regras_chave():
    p = (RAIZ / "sessao/CLAUDE.md").read_text()
    for trecho in ["🔊", "🔇", "[voz]", "[eventos]", "[sistema]", "jarvis confirmar", "jarvis lancar",
                   "jarvis regra adicionar", "--origem voz", "--tecla", "regras.md", "senhor", "geopolítica",
                   "jarvis clima", "orca search", "jarvis calar"]:
        assert trecho in p, trecho
    for antigo in ["Monitor", "--confirmado", "jarvis eventos --seguir"]:
        assert antigo not in p, antigo


def cerebro_settings() -> dict:
    return json.loads((RAIZ / "sessao/cerebro-settings.json").read_text())


def test_cerebro_settings():
    s = cerebro_settings()
    perm = s["permissions"]
    for regra in ["Bash(jarvis lancar:*)", "Bash(jarvis confirmar:*)", "Bash(jarvis regra:*)", "Bash(jarvis enviar:*)",
                  "WebSearch", "mcp__jarvis__permissao"]:
        assert regra in perm["allow"], regra
    for regra in ["Bash(orca terminal send:*)", "Bash(orca agent launch:*)", "Edit", "Write", "Read(//git/**/.env)"]:
        assert regra in perm["deny"], regra
    assert "hooks" not in s and "Monitor" not in perm["allow"]
    assert s["enabledPlugins"]["caveman@caveman"] is False


def test_regras_existe_sem_regra_ativa():
    texto = (RAIZ / "sessao/regras.md").read_text()
    assert "# Regras" in texto
    assert not [linha for linha in texto.splitlines() if linha.startswith("- ")]


def test_nao_ha_persona_na_raiz():
    raiz_settings = RAIZ / ".claude/settings.json"
    assert not raiz_settings.exists() or "hook-fala" not in raiz_settings.read_text()
    assert not Path("/git/CLAUDE.md").exists()
    assert not (RAIZ / "CLAUDE.md").exists() or "🔊" not in (RAIZ / "CLAUDE.md").read_text()


def test_unidades_systemd():
    vigia = (RAIZ / "systemd/jarvis-vigia.service").read_text()
    assert "ExecStart=/usr/bin/python3 /git/jarvis/bin/jarvis vigia" in vigia and "Restart=always" in vigia




def test_unidade_cerebro():
    u = (RAIZ / "systemd/jarvis-cerebro.service").read_text()
    assert "ExecStart=/usr/bin/python3 /git/jarvis/bin/jarvis cerebro" in u and "Restart=always" in u
    assert "linux-orca-cli-shim" in u


def test_autostart_hud():
    d = (RAIZ / "autostart/jarvis-hud.desktop").read_text()
    assert "hud/janela.py" in d and "X-GNOME-Autostart-enabled=true" in d


def test_super_j_abre_hud():
    assert lancador.ATALHOS["jarvis-ouvir"][1].endswith("jarvis hud")


def test_sem_hook_de_fala_nem_aba_antiga():
    assert not (RAIZ / "sessao/jarvis-settings.json").exists()
    assert "Monitor" not in (RAIZ / "sessao/CLAUDE.md").read_text()


def test_iniciar_agora_abre_a_janela(monkeypatch, capsys):
    chamadas = []
    monkeypatch.setattr("jarvis.hud_cli.hud", lambda demo=False: chamadas.append(demo) or 0)
    assert iniciar(env={"ORCA_PANE_KEY": "J", "ORCA_TERMINAL_HANDLE": "term_j"}) == 0
    assert chamadas == [False] and "app" in capsys.readouterr().out


def test_jarvis_sem_argumentos_abre_a_janela(monkeypatch):
    from jarvis import cli
    chamadas = []
    monkeypatch.setattr("jarvis.hud_cli.hud", lambda demo=False: chamadas.append(demo) or 0)
    assert cli.main([]) == 0 and chamadas == [False]
