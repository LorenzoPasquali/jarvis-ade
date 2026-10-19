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
