import json
import os
import sys
import time

from conftest import FIXTURES, RAIZ
from jarvis.cerebro.claude import ProcessoClaude, comando_claude
from jarvis.cerebro.codex import ProcessoCodex

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
    c = comando_claude(RAIZ, "haiku")
    for f in ["-p", "--input-format", "stream-json", "--output-format", "--include-partial-messages", "--verbose",
              "--permission-prompt-tool", "mcp__jarvis__permissao", "--settings", "--mcp-config",
              "--strict-mcp-config"]:
        assert f in c
    assert c[c.index("--setting-sources") + 1] == "project,local"
    mcp = json.loads(c[c.index("--mcp-config") + 1])
    assert mcp["mcpServers"]["jarvis"]["args"] == ["permissao-mcp"]
    assert c[c.index("--model") + 1] == "haiku"


def test_ocupado_so_libera_depois_de_tratar_o_resultado(tmp_path):
    vistos = []
    p = None

    def ao_evento(e):
        if e["type"] == "result":
            vistos.append(p.ocupado)

    p = ProcessoClaude([sys.executable, FALSO], tmp_path, os.environ.copy(), ao_evento, tmp_path / "s.json")
    p.iniciar()
    p.enviar("oi")
    esperar(lambda: vistos)
    assert vistos == [True]
    esperar(lambda: not p.ocupado)
    p.parar()


MORRE_LOGO = [sys.executable, "-c", "import sys; sys.exit(1)"]


def test_falhas_rapidas_seguidas_descartam_a_sessao(tmp_path):
    (tmp_path / "s.json").write_text('{"session_id": "corrompida"}')
    eventos = []
    p = ProcessoClaude(MORRE_LOGO, tmp_path, os.environ.copy(), eventos.append, tmp_path / "s.json",
                       espera_reinicio=0.05)
    p.iniciar()
    esperar(lambda: not (tmp_path / "s.json").exists(), limite=6)
    p.parar()


def test_avisa_quando_fica_pronto(tmp_path):
    eventos = []
    p = ProcessoClaude([sys.executable, FALSO], tmp_path, os.environ.copy(), eventos.append, tmp_path / "s.json")
    p.iniciar()
    assert {"type": "jarvis_pronto"} in eventos
    p.parar()


def test_reiniciar_libera_turno_travado(tmp_path):
    eventos = []
    trava = [sys.executable, "-c", "import sys, time\nfor l in sys.stdin: time.sleep(60)"]
    p = ProcessoClaude(trava, tmp_path, os.environ.copy(), eventos.append, tmp_path / "s.json",
                       espera_reinicio=0.05)
    p.iniciar()
    p.enviar("oi")
    p.reiniciar()
    esperar(lambda: any(e.get("subtype") == "error_restart" for e in eventos), limite=6)
    assert not p.ocupado
    p.parar()


def test_parar_durante_a_espera_do_reinicio_nao_sobe_outro(tmp_path):
    eventos = []
    p = ProcessoClaude(MORRE_LOGO, tmp_path, os.environ.copy(), eventos.append, tmp_path / "s.json",
                       espera_reinicio=0.3)
    p.iniciar()
    esperar(lambda: {"type": "jarvis_reiniciando"} in eventos)
    p.parar()
    prontos = eventos.count({"type": "jarvis_pronto"})
    time.sleep(1.0)
    assert eventos.count({"type": "jarvis_pronto"}) == prontos


def test_codex_converte_resposta_jsonl_em_eventos_do_cerebro(tmp_path):
    eventos = []
    p = ProcessoCodex([sys.executable, FALSO.replace("claude_falso", "codex_falso")], tmp_path,
                      os.environ.copy(), eventos.append, tmp_path / "codex-s.json")
    p.enviar("oi")
    esperar(lambda: any(e["type"] == "result" for e in eventos))
    assert not p.ocupado
    assert json.loads((tmp_path / "codex-s.json").read_text())["thread_id"] == "thread-teste"
    deltas = "".join(e["event"]["delta"]["text"] for e in eventos if e["type"] == "stream_event")
    assert deltas == "Olá, senhor.\n🔊 Fallback pronto.\n"
    assert [e for e in eventos if e["type"] == "result"][-1]["result"] == deltas


def test_codex_reutiliza_a_thread_no_proximo_fallback(tmp_path):
    (tmp_path / "codex-s.json").write_text('{"thread_id": "thread-anterior"}')
    p = ProcessoCodex(["codex", "exec"], tmp_path, os.environ.copy(), lambda e: None, tmp_path / "codex-s.json")
    assert p.comando_atual("oi")[:4] == ["codex", "exec", "resume", "thread-anterior"]
