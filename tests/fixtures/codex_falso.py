"""Imita a saída JSONL de `codex exec --json` para os testes."""

import json
import sys


def emitir(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


emitir({"type": "thread.started", "thread_id": "thread-teste"})
emitir({"type": "turn.started"})
if "reconecta" in sys.argv[-1]:
    emitir({"type": "error", "message": "Reconnecting... 1/5 (stream disconnected)"})
emitir({"type": "item.completed", "item": {"type": "agent_message", "text": "Olá, senhor.\n🔊 Fallback pronto.\n"}})
emitir({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}})
