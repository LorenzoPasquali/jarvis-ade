"""Um `claude -p` em stream-json que fica vivo entre as mensagens e é retomado se cair."""

import json
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path


def comando_claude(raiz: Path, modelo: str) -> list[str]:
    mcp = {"mcpServers": {"jarvis": {"command": str(raiz / "bin/jarvis"), "args": ["permissao-mcp"]}}}
    return ["claude", "-p", "--input-format", "stream-json", "--output-format", "stream-json",
            "--include-partial-messages", "--verbose", "--model", modelo,
            "--settings", str(raiz / "sessao/cerebro-settings.json"),
            # Só o MCP do Jarvis e só as configurações do projeto: sem os plugins, conectores e hooks do usuário,
            # que enchiam o contexto (~40 mil tokens a cada turno) e deixavam o Jarvis lento.
            "--setting-sources", "project,local", "--strict-mcp-config",
            "--mcp-config", json.dumps(mcp), "--permission-prompt-tool", "mcp__jarvis__permissao"]


class ProcessoClaude:
    def __init__(self, comando: list[str], cwd: Path, env: dict, ao_evento: Callable[[dict], None],
                 arquivo_sessao: Path, espera_reinicio: float = 2.0):
        self._comando = list(comando)
        self._cwd = cwd
        self._env = env
        self._ao_evento = ao_evento
        self._arquivo_sessao = arquivo_sessao
        self._espera_reinicio = espera_reinicio
        self._proc: subprocess.Popen | None = None
        self._trava = threading.Lock()
        self._parando = False
        self._pendente: str | None = None
        self._inicio = 0.0
        self._falhas_rapidas = 0
        self.ocupado = False

    def _sessao(self) -> str | None:
        try:
            return json.loads(self._arquivo_sessao.read_text()).get("session_id")
        except (FileNotFoundError, ValueError):
            return None

    def _gravar_sessao(self, session_id: str) -> None:
        self._arquivo_sessao.write_text(json.dumps({"session_id": session_id}))

    def comando_atual(self) -> list[str]:
        sessao = self._sessao()
        return [*self._comando, "--resume", sessao] if sessao else list(self._comando)

    def iniciar(self) -> None:
        with self._trava:
            self._parando = False
            self._proc = subprocess.Popen(self.comando_atual(), cwd=self._cwd, env=self._env, text=True,
                                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=1)
            self._inicio = time.time()
            threading.Thread(target=self._ler, args=(self._proc,), daemon=True).start()
            pendente, self._pendente = self._pendente, None
        self._ao_evento({"type": "jarvis_pronto"})
        if pendente is not None:
            self.enviar(pendente)

    def reiniciar(self) -> None:
        """Mata o processo travado; o leitor percebe a saída e sobe outro (com --resume)."""
        if self._proc and self._proc.poll() is None:
            self._proc.kill()

    def enviar(self, texto: str) -> None:
        """Entrega a mensagem; se o processo estiver reiniciando, ela sai assim que ele voltar."""
        linha = json.dumps({"type": "user", "message": {"role": "user", "content": texto}}, ensure_ascii=False)
        with self._trava:
            self.ocupado = True
            try:
                self._proc.stdin.write(linha + "\n")
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError, ValueError, AttributeError):  # ainda subindo ou reiniciando
                self._pendente = texto

    def parar(self) -> None:
        self._parando = True
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()

    def _ler(self, proc: subprocess.Popen) -> None:
        for linha in proc.stdout:
            try:
                evento = json.loads(linha)
            except ValueError:
                continue
            if evento.get("session_id") and evento.get("type") in ("system", "result"):
                self._gravar_sessao(evento["session_id"])
            self._ao_evento(evento)
            if evento.get("type") == "result":
                self.ocupado = False  # só depois de o resultado ser tratado: evita começar outro turno no meio
        proc.wait()
        if self._parando:
            return
        self._ao_evento({"type": "jarvis_reiniciando"})
        if self.ocupado:
            self._ao_evento({"type": "result", "subtype": "error_restart", "is_error": True, "result": ""})
            self.ocupado = False
        # Morrer logo depois de subir, várias vezes seguidas, costuma ser sessão que não retoma: começa outra.
        self._falhas_rapidas = self._falhas_rapidas + 1 if time.time() - self._inicio < 10 else 0
        if self._falhas_rapidas >= 3:
            self._arquivo_sessao.unlink(missing_ok=True)
        espera = min(60.0, self._espera_reinicio * 2 ** min(self._falhas_rapidas, 5))
        while not self._parando:
            time.sleep(espera)
            if self._parando:  # mandaram parar durante a espera
                return
            try:
                self.iniciar()
                return
            except OSError:
                espera = min(60.0, espera * 2)
