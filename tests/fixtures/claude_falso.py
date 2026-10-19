"""Imita `claude -p --input-format stream-json --output-format stream-json` para os testes."""
import json
import sys


def emitir(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


iniciado = False
for linha in sys.stdin:
    if not linha.strip():
        continue
    texto = json.loads(linha)["message"]["content"]
    if not iniciado:
        emitir({"type": "system", "subtype": "init", "session_id": "sess-teste", "model": "claude-sonnet-5-5"})
        iniciado = True
    if "MORRA" in texto:
        sys.exit(1)
    resposta = "Olá, senhor.\n🔊 Tudo certo.\n"
    for pedaco in ["Olá, senhor.\n", "🔊 Tudo ", "certo.\n"]:
        emitir({"type": "stream_event", "event": {"type": "content_block_delta", "index": 0,
                                                   "delta": {"type": "text_delta", "text": pedaco}}})
    emitir({"type": "assistant", "message": {"content": [{"type": "text", "text": resposta}]}})
    emitir({"type": "result", "subtype": "success", "result": resposta, "session_id": "sess-teste", "is_error": False})
