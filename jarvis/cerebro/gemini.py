"""Adaptador de `agy` em stream-json para o protocolo interno do cérebro."""

import json
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path


def comando_gemini(modelo: str = "gemini-3.8-flash-medium") -> list[str]:
    return ["agy", "--model", modelo, "--agent", "jarvis-fallback",
            "--add-dir", "/git",
            "--input-format", "stream-json", "--output-format", "stream-json"]


class ProcessoGemini:
    """Mantém uma conversa Antigravity, iniciada somente quando o Claude falha."""

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

    def _conversa(self) -> str | None:
        try:
            return json.loads(self._arquivo_sessao.read_text(encoding="utf-8")).get("conversation_id")
        except (FileNotFoundError, ValueError, OSError):
            return None

    def _gravar_conversa(self, conversation_id: str) -> None:
        try:
            self._arquivo_sessao.parent.mkdir(parents=True, exist_ok=True)
            self._arquivo_sessao.write_text(json.dumps({"conversation_id": conversation_id}), encoding="utf-8")
        except OSError as erro:
            print(f"cérebro: não consegui salvar a sessão do Gemini: {erro}", flush=True)

    def comando_atual(self) -> list[str]:
        conversa = self._conversa()
        comando = list(self._comando)
        if conversa:
            comando.extend(["--conversation", conversa])
        return comando

    def _entrada(self, texto: str) -> str:
        try:
            instrucoes = self._persona.read_text(encoding="utf-8") if self._persona else ""
        except OSError:
            instrucoes = ""
        return ("Você é o Jarvis. Siga a persona abaixo, exceto onde a mensagem do modo reserva disser o "
                "contrário (no modo reserva você não roda comandos).\n\n"
                f"{instrucoes}\n\n"
                f"{texto}")

    def enviar(self, texto: str) -> None:
        falha = None
        with self._trava:
            if self.ocupado:
                return
            self.ocupado = True
            conversa_existente = self._conversa()
            proc = self._proc
            try:
                if proc is None or proc.poll() is not None:
                    proc = subprocess.Popen(self.comando_atual(), cwd=self._cwd, env=self._env, text=True,
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, bufsize=1)
                    self._proc = proc
                    threading.Thread(target=self._ler, args=(proc,), daemon=True).start()
                mensagem = {"event": "user", "message": {
                    "content": texto if conversa_existente else self._entrada(texto)}}
                proc.stdin.write(json.dumps(mensagem, ensure_ascii=False) + "\n")
                proc.stdin.flush()
            except (OSError, BrokenPipeError, AttributeError, ValueError) as erro:
                falha = str(erro)
                self.ocupado = False
                if proc and proc.poll() is None:
                    proc.kill()
        if falha:
            self._ao_evento({"type": "result", "is_error": True, "result": falha})

    def reiniciar(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.kill()

    def parar(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()

    def _ler(self, proc: subprocess.Popen) -> None:
        resultado_recebido = False
        try:
            for linha in proc.stdout:
                try:
                    evento = json.loads(linha)
                except (TypeError, ValueError):
                    continue  # ignora diagnósticos não JSON mesclados com stdout

                tipo = evento.get("event")
                if tipo == "init":
                    conversation_id = evento.get("conversation_id")
                    if conversation_id:
                        self._gravar_conversa(conversation_id)
                    self._ao_evento({"type": "progress"})
                elif tipo == "step_update":
                    etapa = evento.get("step_update") or {}
                    conversation_id = etapa.get("conversation_id")
                    if conversation_id:
                        self._gravar_conversa(conversation_id)
                    delta = etapa.get("text_delta") or ""
                    if etapa.get("step_type") == "agent_response" and delta:
                        self._ao_evento({"type": "stream_event", "event": {
                            "type": "content_block_delta",
                            "delta": {"type": "text_delta", "text": delta}}})
                    else:
                        self._ao_evento({"type": "progress"})
                elif tipo == "result":
                    resultado = evento.get("result") or {}
                    conversation_id = resultado.get("conversation_id")
                    if conversation_id:
                        self._gravar_conversa(conversation_id)
                    status = resultado.get("status")
                    self._ao_evento({"type": "result", "is_error": status != "SUCCESS",
                                     "result": resultado.get("response") or resultado.get("error") or ""})
                    resultado_recebido = True
                    with self._trava:
                        self.ocupado = False
        finally:
            proc.wait()
            with self._trava:
                if self._proc is proc:
                    self._proc = None
                ficou_ocupado = self.ocupado
                self.ocupado = False
            if ficou_ocupado and not resultado_recebido:
                self._ao_evento({"type": "result", "is_error": True,
                                 "result": "O processo do Antigravity encerrou antes de responder."})
