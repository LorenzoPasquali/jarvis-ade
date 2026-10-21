"""Adaptador de `codex exec --json` para o protocolo interno do cérebro."""

import json
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path


def comando_codex(modelo: str | None = None) -> list[str]:
    comando = ["codex", "exec"]
    if modelo:
        comando.extend(["--model", modelo])
    return comando


class ProcessoCodex:
    """Executa um turno Codex quando o Claude não pode responder."""

    def __init__(self, comando: list[str], cwd: Path, env: dict, ao_evento: Callable[[dict], None],
                 arquivo_sessao: Path, persona: Path | None = None):
        self._comando = list(comando)
        self._cwd = cwd
        self._env = env
        self._ao_evento = ao_evento
        self._arquivo_sessao = arquivo_sessao
        self._persona = persona
        self._proc: subprocess.Popen | None = None
        self._trava = threading.Lock()
        self.ocupado = False

    def _thread(self) -> str | None:
        try:
            return json.loads(self._arquivo_sessao.read_text()).get("thread_id")
        except (FileNotFoundError, ValueError):
            return None

    def _gravar_thread(self, thread_id: str) -> None:
        self._arquivo_sessao.write_text(json.dumps({"thread_id": thread_id}))

    def _entrada(self, texto: str) -> str:
        if self._thread() or self._persona is None:
            return texto
        try:
            instrucoes = self._persona.read_text(encoding="utf-8")
        except OSError:
            instrucoes = ""
        return ("Você é o fallback temporário do Jarvis. Siga integralmente estas instruções permanentes "
                "e responda à mensagem atual. Não edite arquivos.\n\n"
                f"{instrucoes}\n\nMensagem atual:\n{texto}")

    def comando_atual(self, texto: str) -> list[str]:
        thread_id = self._thread()
        if thread_id:
            return [*self._comando, "resume", thread_id, "--json", "--skip-git-repo-check", texto]
        return [*self._comando, "--json", "--sandbox", "workspace-write", "--skip-git-repo-check", texto]

    def enviar(self, texto: str) -> None:
        with self._trava:
            if self.ocupado:
                return
            self.ocupado = True
        threading.Thread(target=self._executar, args=(self._entrada(texto),), daemon=True).start()

    def reiniciar(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.kill()

    def parar(self) -> None:
        self.reiniciar()

    def _delta(self, texto: str) -> None:
        if texto:
            self._ao_evento({"type": "stream_event", "event": {"type": "content_block_delta",
                            "delta": {"type": "text_delta", "text": texto}}})

    def _executar(self, texto: str) -> None:
        concluido, falhou, resposta = False, "", ""
        try:
            self._proc = subprocess.Popen(self.comando_atual(texto), cwd=self._cwd, env=self._env, text=True,
                                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1)
            for linha in self._proc.stdout:
                try:
                    evento = json.loads(linha)
                except ValueError:
                    continue
                tipo = evento.get("type")
                if tipo == "thread.started" and evento.get("thread_id"):
                    self._gravar_thread(evento["thread_id"])
                elif tipo == "item.completed":
                    item = evento.get("item") or {}
                    if item.get("type") == "agent_message":
                        trecho = item.get("text") or ""
                        resposta += trecho
                        self._delta(trecho)
                elif tipo == "item.agent_message.delta":
                    trecho = evento.get("delta") or ""
                    resposta += trecho
                    self._delta(trecho)
                elif tipo == "turn.completed":
                    concluido = True
                elif tipo in ("turn.failed", "error"):
                    falhou = json.dumps(evento, ensure_ascii=False)
            codigo = self._proc.wait()
            if not concluido and not falhou:
                falhou = f"Codex terminou com código {codigo}."
        except OSError as erro:
            falhou = str(erro)
        finally:
            resultado = falhou if falhou else resposta
            self._ao_evento({"type": "result", "is_error": bool(falhou), "result": resultado})
            with self._trava:
                self.ocupado = False
