import json
import os
import sys
import time

from conftest import FIXTURES, RAIZ
from jarvis.cerebro.claude import ProcessoClaude, comando_claude

FALSO = str(FIXTURES / "claude_falso.py")


def esperar(condicao, limite=4.0):
    fim = time.time() + limite
    while time.time() < fim:
        if condicao():
            return
        time.sleep(0.02)
    raise AssertionError("condição não atingida")


def test_resposta_completa_e_sessao_gravada(tmp_path):
    eventos = []
    p = ProcessoClaude([sys.executable, FALSO], tmp_path, os.environ.copy(), eventos.append, tmp_path / "s.json")
    p.iniciar()
    p.enviar("oi")
    esperar(lambda: any(e["type"] == "result" for e in eventos))
    assert not p.ocupado and json.loads((tmp_path / "s.json").read_text())["session_id"] == "sess-teste"
    deltas = "".join(e["event"]["delta"]["text"] for e in eventos
                     if e["type"] == "stream_event" and e["event"]["type"] == "content_block_delta")
    assert deltas == "Olá, senhor.\n🔊 Tudo certo.\n"
    p.parar()


def test_retoma_sessao_ao_reiniciar(tmp_path):
    (tmp_path / "s.json").write_text('{"session_id": "abc"}')
    p = ProcessoClaude([sys.executable, FALSO], tmp_path, os.environ.copy(), lambda e: None, tmp_path / "s.json")
    assert p.comando_atual()[-2:] == ["--resume", "abc"]


def test_morte_no_meio_libera_e_reinicia(tmp_path):
    eventos = []
    p = ProcessoClaude([sys.executable, FALSO], tmp_path, os.environ.copy(), eventos.append, tmp_path / "s.json",
                       espera_reinicio=0.1)
    p.iniciar()
    p.enviar("MORRA")
    esperar(lambda: any(e.get("subtype") == "error_restart" for e in eventos), limite=6)
    assert not p.ocupado and any(e["type"] == "jarvis_reiniciando" for e in eventos)
    p.enviar("oi")
    esperar(lambda: sum(e["type"] == "result" for e in eventos) >= 2, limite=6)
    p.parar()


def test_comando_claude_tem_flags():
    c = comando_claude(RAIZ, "sonnet")
    for f in ["-p", "--input-format", "stream-json", "--output-format", "--include-partial-messages", "--verbose",
              "--permission-prompt-tool", "mcp__jarvis__permissao", "--settings", "--mcp-config"]:
        assert f in c
    mcp = json.loads(c[c.index("--mcp-config") + 1])
    assert mcp["mcpServers"]["jarvis"]["args"] == ["permissao-mcp"]
    assert c[c.index("--model") + 1] == "sonnet"
