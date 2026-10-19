import json
import os
import subprocess

from conftest import RAIZ
from jarvis.permissao_mcp import decidir


def conversa(mensagens):
    entrada = "".join(json.dumps(m) + "\n" for m in mensagens)
    env = {**os.environ, "JARVIS_CEREBRO_URL": "http://127.0.0.1:9"}  # porta fechada: sem cérebro
    proc = subprocess.run([str(RAIZ / "bin/jarvis"), "permissao-mcp"], input=entrada, capture_output=True,
                          text=True, timeout=10, env=env)
    return [json.loads(linha) for linha in proc.stdout.splitlines() if linha.strip()]


def test_initialize_e_lista():
    r = conversa([{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                  {"jsonrpc": "2.0", "method": "notifications/initialized"},
                  {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}])
    assert len(r) == 2
    assert r[0]["result"]["serverInfo"]["name"] == "jarvis" and r[0]["result"]["protocolVersion"] == "2025-06-18"
    ferramenta = r[1]["result"]["tools"][0]
    assert ferramenta["name"] == "permissao" and ferramenta["inputSchema"]["required"] == ["tool_name", "input"]


def test_chamada_sem_cerebro_nega_pelo_protocolo():
    r = conversa([{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                  {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                   "params": {"name": "permissao", "arguments": {"tool_name": "Bash", "input": {"command": "ls"}}}}])
    decisao = json.loads(r[1]["result"]["content"][0]["text"])
    assert decisao["behavior"] == "deny"


def test_metodo_desconhecido_responde_erro():
    r = conversa([{"jsonrpc": "2.0", "id": 9, "method": "nada/existe"}])
    assert r[0]["error"]["code"] == -32601


def test_decidir_aprovado_e_negado():
    assert decidir("Bash", {"command": "ls"}, perguntar=lambda f, e: {"aprovado": True}) == \
        {"behavior": "allow", "updatedInput": {"command": "ls"}}
    assert decidir("Bash", {}, perguntar=lambda f, e: {"aprovado": False})["behavior"] == "deny"


def test_decidir_sem_cerebro_nega():
    def falha(f, e):
        raise OSError()
    negado = decidir("Bash", {}, perguntar=falha)
    assert negado == {"behavior": "deny", "message": "O senhor não respondeu; não fiz isso."}
