"""`jarvis hud`: mostra a janela do Jarvis (Super+J) e avisa o cérebro para começar a ouvir."""

import json
import os
import signal
import subprocess
import urllib.request

from jarvis.config import RAIZ, dados

URL_CEREBRO = "http://127.0.0.1:8766"


def _janela_viva(pid: int) -> bool:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return b"hud/janela.py" in f.read()
    except OSError:
        return False


def chamar_cerebro(rota: str, corpo: dict | None = None) -> bool:
    req = urllib.request.Request(f"{URL_CEREBRO}{rota}", data=json.dumps(corpo or {}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=2).close()
    except OSError:
        return False
    return True


def _avisar_cerebro() -> None:
    chamar_cerebro("/api/super-j")


def _iniciar_janela(demo: bool) -> None:
    comando = ["/usr/bin/python3", str(RAIZ / "hud/janela.py"), "--mostrar"]
    if demo:
        comando += ["--url", (RAIZ / "hud/index.html").as_uri() + "?demo=1"]
    subprocess.Popen(comando, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _pid() -> int:
    try:
        return int((dados() / "hud.pid").read_text())
    except (FileNotFoundError, ValueError):
        return 0


def janela_rodando() -> bool:
    pid = _pid()
    return bool(pid) and _janela_viva(pid)


def hud(demo: bool = False) -> int:
    pid = _pid()
    if pid and _janela_viva(pid):
        os.kill(pid, signal.SIGUSR1)
    else:
        _iniciar_janela(demo)
    if not demo:
        _avisar_cerebro()
    return 0

