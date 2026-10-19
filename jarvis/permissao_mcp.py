"""Servidor MCP (stdio) usado como `--permission-prompt-tool` do cérebro.

Quando o Claude headless quer usar algo que as permissões não liberam, pergunta aqui; a pergunta vira um
cartão Aprovar/Recusar na janela do Jarvis. Sem resposta, nega.
"""

import json
import os
import sys
import urllib.request

NEGADO_SEM_RESPOSTA = "O senhor não respondeu; não fiz isso."
FERRAMENTA = {
    "name": "permissao",
    "description": "Pergunta ao senhor, pela janela do Jarvis, se uma ação pode ser feita.",
    "inputSchema": {"type": "object",
                    "properties": {"tool_name": {"type": "string"}, "input": {"type": "object"}},
                    "required": ["tool_name", "input"]},
}


def _url_cerebro() -> str:
    return os.environ.get("JARVIS_CEREBRO_URL", "http://127.0.0.1:8766")


def _perguntar_cerebro(ferramenta: str, entrada: dict) -> dict:
    corpo = json.dumps({"ferramenta": ferramenta, "entrada": entrada}).encode()
    req = urllib.request.Request(f"{_url_cerebro()}/api/permissao", data=corpo,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=130) as resposta:
        return json.load(resposta)


def decidir(tool_name: str, entrada: dict, perguntar=_perguntar_cerebro) -> dict:
    try:
        aprovado = bool(perguntar(tool_name, entrada).get("aprovado"))
    except (OSError, ValueError):
        return {"behavior": "deny", "message": NEGADO_SEM_RESPOSTA}
    if aprovado:
        return {"behavior": "allow", "updatedInput": entrada}
    return {"behavior": "deny", "message": "O senhor recusou."}


def _responder(pedido: dict) -> dict | None:
    if "id" not in pedido:
        return None  # notificação
    metodo, params = pedido.get("method"), pedido.get("params") or {}
    if metodo == "initialize":
        resultado = {"protocolVersion": params.get("protocolVersion", "2025-06-18"),
                     "capabilities": {"tools": {}}, "serverInfo": {"name": "jarvis", "version": "1"}}
    elif metodo == "tools/list":
        resultado = {"tools": [FERRAMENTA]}
    elif metodo == "tools/call":
        argumentos = params.get("arguments") or {}
        decisao = decidir(str(argumentos.get("tool_name", "")), argumentos.get("input") or {})
        resultado = {"content": [{"type": "text", "text": json.dumps(decisao, ensure_ascii=False)}]}
    elif metodo == "ping":
        resultado = {}
    else:
        return {"jsonrpc": "2.0", "id": pedido["id"], "error": {"code": -32601, "message": "método desconhecido"}}
    return {"jsonrpc": "2.0", "id": pedido["id"], "result": resultado}


def servir(entrada=sys.stdin, saida=sys.stdout) -> None:
    for linha in entrada:
        if not linha.strip():
            continue
        try:
            resposta = _responder(json.loads(linha))
        except ValueError:
            resposta = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "JSON inválido"}}
        if resposta is not None:
            saida.write(json.dumps(resposta, ensure_ascii=False) + "\n")
            saida.flush()
