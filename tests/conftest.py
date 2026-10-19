import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(RAIZ))


@pytest.fixture
def dados_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DADOS", str(tmp_path))
    return tmp_path


def carregar(nome: str) -> dict:
    return json.loads((FIXTURES / nome).read_text(encoding="utf-8"))


def ag(pane: str, estado: str, projeto: str | None = None, mensagem: str = "", worktree: str | None = None):
    from jarvis.orca import Agente

    projeto = projeto or f"proj-{pane.lower()}"
    return Agente(pane_key=pane, projeto=projeto, worktree=worktree or projeto, caminho=f"/git/{projeto}",
                  agente="claude", estado=estado, ultima_mensagem=mensagem, prompt="",
                  estado_desde_ms=1792422000000, ferramenta=None)
