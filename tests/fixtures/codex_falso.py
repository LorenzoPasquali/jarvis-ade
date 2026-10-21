"""Imita a saída JSONL de `codex exec --json` para os testes."""

import json
import sys


def emitir(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


emitir({"type": "thread.started", "thread_id": "thread-teste"})
emitir({"type": "turn.started"})
emitir({"type": "item.completed", "item": {"type": "agent_message", "text": "Olá, senhor.\n🔊 Fallback pronto.\n"}})
emitir({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}})
