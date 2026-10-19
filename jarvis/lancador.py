"""Abre a sessão do Jarvis num terminal do Orca e instala serviços, comando e atalhos."""

import ast
import os
import shutil
import subprocess
from pathlib import Path

from jarvis import sessao
from jarvis.config import RAIZ

SERVICOS = ("jarvis-voz", "jarvis-vigia")
MENSAGEM_INICIAL = "[sistema] Sessão do Jarvis iniciada."
_CHAVE_ATALHOS = "org.gnome.settings-daemon.plugins.media-keys"
_ESQUEMA_ATALHO = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
_BASE_ATALHO = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings"
ATALHOS = {
    "jarvis-ouvir": ("Jarvis: falar", f"{RAIZ / 'bin/jarvis'} ouvir", "<Super>j"),
    "jarvis-calar": ("Jarvis: silêncio", f"{RAIZ / 'bin/jarvis'} calar", "<Super><Shift>j"),
}


def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True)


def garantir_servicos() -> None:
    for servico in SERVICOS:
        if _systemctl("is-active", "--quiet", servico).returncode == 0:
            continue
        if _systemctl("start", servico).returncode != 0:
            print(f"Aviso: o serviço {servico} não está rodando. Rode `jarvis instalar`.")


def iniciar(env=os.environ, execvpe=os.execvpe) -> int:
    pane, terminal = env.get("ORCA_PANE_KEY"), env.get("ORCA_TERMINAL_HANDLE")
    if not pane or not terminal:
        print("Abra o Jarvis num terminal do Orca.")
        return 1
    sessao.registrar(pane, terminal)
    garantir_servicos()
    novo_env = dict(env)
    novo_env["PATH"] = f"{RAIZ / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    os.chdir(RAIZ / "sessao")
    execvpe("claude", ["claude", "--settings", str(RAIZ / "sessao/jarvis-settings.json"), MENSAGEM_INICIAL],
            novo_env)
    return 0


def _instalar_atalhos() -> None:
    atual = subprocess.run(["gsettings", "get", _CHAVE_ATALHOS, "custom-keybindings"],
                           capture_output=True, text=True).stdout.strip()
    lista = [] if atual.startswith("@as") else ast.literal_eval(atual or "[]")
    for nome, (titulo, comando, tecla) in ATALHOS.items():
        caminho = f"{_BASE_ATALHO}/{nome}/"
        if caminho not in lista:
            lista.append(caminho)
        for chave, valor in (("name", titulo), ("command", comando), ("binding", tecla)):
            subprocess.run(["gsettings", "set", f"{_ESQUEMA_ATALHO}:{caminho}", chave, valor], check=True)
    subprocess.run(["gsettings", "set", _CHAVE_ATALHOS, "custom-keybindings", str(lista)], check=True)


def instalar() -> int:
    destino = Path.home() / ".config/systemd/user"
    destino.mkdir(parents=True, exist_ok=True)
    for servico in SERVICOS:
        shutil.copy(RAIZ / "systemd" / f"{servico}.service", destino / f"{servico}.service")
    _systemctl("daemon-reload")
    for servico in SERVICOS:
        if _systemctl("enable", "--now", servico).returncode != 0:
            print(f"Falha ao ativar {servico}: veja `journalctl --user -u {servico}`.")
            return 1
    atalho = Path.home() / ".local/bin/jarvis"
    atalho.parent.mkdir(parents=True, exist_ok=True)
    if atalho.is_symlink() or atalho.exists():
        atalho.unlink()
    atalho.symlink_to(RAIZ / "bin/jarvis")
    _instalar_atalhos()
    print("Instalado: serviços jarvis-voz e jarvis-vigia, comando `jarvis`, atalhos Super+J (falar) e "
          "Super+Shift+J (silêncio).")
    return 0
