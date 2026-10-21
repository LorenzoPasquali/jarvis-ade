"""Abre a sessão do Jarvis num terminal do Orca e instala serviços, comando e atalhos."""

import ast
import json
import os
import signal
import shutil
import subprocess
from pathlib import Path

from jarvis.config import RAIZ, dados

SERVICOS = ("jarvis-voz", "jarvis-vigia", "jarvis-cerebro")
_CHAVE_ATALHOS = "org.gnome.settings-daemon.plugins.media-keys"
_ESQUEMA_ATALHO = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
_BASE_ATALHO = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings"
ATALHOS = {
    "jarvis-ouvir": ("Jarvis: falar", f"{RAIZ / 'bin/jarvis'} hud", "<Super>j"),
    "jarvis-calar": ("Jarvis: silêncio", f"{RAIZ / 'bin/jarvis'} calar", "<Super><Shift>j"),
}


def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True)


def iniciar(env=os.environ) -> int:
    """Compatibilidade: o Jarvis não roda mais numa aba do Orca; agora é o app (Super+J)."""
    from jarvis import hud_cli

    print("O Jarvis agora é um app sempre ligado: Super+J abre a janela.")
    return hud_cli.hud()


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


def _e_gravador(pid: int) -> bool:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return b"pw-record" in f.read()
    except OSError:
        return False


def parar_gravador_antigo() -> None:
    """O aperta-e-fala antigo (`jarvis ouvir`) podia deixar um pw-record gravando sem fim."""
    arquivo = dados() / "ptt.json"
    try:
        pid = int(json.loads(arquivo.read_text())["pid"])
    except (FileNotFoundError, ValueError, KeyError, TypeError):
        return
    if _e_gravador(pid):
        os.kill(pid, signal.SIGINT)
    arquivo.unlink(missing_ok=True)


def instalar() -> int:
    parar_gravador_antigo()
    destino = Path.home() / ".config/systemd/user"
    destino.mkdir(parents=True, exist_ok=True)
    for servico in SERVICOS:
        shutil.copy(RAIZ / "systemd" / f"{servico}.service", destino / f"{servico}.service")
    _systemctl("daemon-reload")
    for servico in SERVICOS:
        if _systemctl("enable", "--now", servico).returncode != 0:
            print(f"Falha ao ativar {servico}: veja `journalctl --user -u {servico}`.")
            return 1
    autostart = Path.home() / ".config/autostart"
    autostart.mkdir(parents=True, exist_ok=True)
    shutil.copy(RAIZ / "autostart/jarvis-hud.desktop", autostart / "jarvis-hud.desktop")
    atalho = Path.home() / ".local/bin/jarvis"
    atalho.parent.mkdir(parents=True, exist_ok=True)
    if atalho.is_symlink() or atalho.exists():
        atalho.unlink()
    atalho.symlink_to(RAIZ / "bin/jarvis")
    _instalar_atalhos()
    from jarvis import hud_cli

    if not hud_cli.janela_rodando():
        subprocess.Popen(["/usr/bin/python3", str(RAIZ / "hud/janela.py")], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("Instalado: serviços jarvis-voz, jarvis-vigia e jarvis-cerebro, a janela no login, o comando `jarvis`, "
          "atalhos Super+J (falar com o Jarvis) e Super+Shift+J (silêncio).")
    return 0
