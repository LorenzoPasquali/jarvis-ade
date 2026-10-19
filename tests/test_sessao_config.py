import json
import os
from pathlib import Path

import pytest

from conftest import RAIZ
from jarvis import lancador, sessao
from jarvis.lancador import iniciar


def settings() -> dict:
    return json.loads((RAIZ / "sessao/jarvis-settings.json").read_text())


def test_settings_validos():
    s = settings()
    assert "Bash(orca terminal send:*)" in s["permissions"]["deny"]
    assert "Bash(jarvis enviar:*)" in s["permissions"]["allow"] and "Monitor" in s["permissions"]["allow"]
    assert s["permissions"]["additionalDirectories"] == ["/git"]
    gancho = s["hooks"]["Stop"][0]["hooks"][0]
    assert gancho.get("async", False) is False  # async se perde quando o claude encerra
    executavel = gancho["command"].split()[0]
    assert executavel == str(RAIZ / "bin/jarvis") and os.access(executavel, os.X_OK)


def test_settings_desligam_plugins_que_mudam_o_tom():
    plugins = settings()["enabledPlugins"]
    assert plugins["caveman@caveman"] is False and plugins["superpowers@claude-plugins-official"] is False


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


def test_iniciar_fora_do_orca_recusa(capsys):
    assert iniciar(env={}, execvpe=lambda *a: pytest.fail("não deveria executar")) == 1
    assert "terminal do Orca" in capsys.readouterr().out


def test_iniciar_registra_e_executa_claude(dados_tmp, monkeypatch):
    monkeypatch.setattr(lancador, "garantir_servicos", lambda: None)
    monkeypatch.setattr(lancador.os, "chdir", lambda caminho: None)
    chamadas = []
    iniciar(env={"ORCA_PANE_KEY": "J", "ORCA_TERMINAL_HANDLE": "term_j", "PATH": "/usr/bin"},
            execvpe=lambda prog, args, env: chamadas.append((prog, args, env)))
    prog, args, env = chamadas[0]
    assert prog == "claude" and args[args.index("--settings") + 1] == str(RAIZ / "sessao/jarvis-settings.json")
    assert args[-1] == "[sistema] Sessão do Jarvis iniciada."
    assert env["PATH"].startswith(str(RAIZ / "bin")) and sessao.ler()["terminal"] == "term_j"


def test_unidades_systemd():
    vigia = (RAIZ / "systemd/jarvis-vigia.service").read_text()
    assert "ExecStart=/usr/bin/python3 /git/jarvis/bin/jarvis vigia" in vigia and "Restart=always" in vigia


def test_permissoes_contra_injecao():
    perm = settings()["permissions"]
    assert "WebFetch" not in perm["allow"] and "WebSearch" in perm["allow"]
    assert "Edit(//git/jarvis/sessao/regras.md)" in perm["ask"]
    assert not [r for r in perm["allow"] if r.startswith("Edit(")]
    for segredo in ["Read(//git/**/.env)", "Read(//git/**/.env.*)", "Read(~/.ssh/**)"]:
        assert segredo in perm["deny"]
