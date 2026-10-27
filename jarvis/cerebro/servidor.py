"""Servidor local da janela: arquivos da interface, SSE com os eventos do cérebro e as ações do usuário."""

import json
import queue
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from jarvis.config import RAIZ

TIPOS = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".js": "text/javascript; charset=utf-8", ".woff2": "font/woff2", ".svg": "image/svg+xml",
         ".png": "image/png", ".txt": "text/plain; charset=utf-8"}


def criar(cerebro, porta: int = 8766, pasta_hud: Path = RAIZ / "hud") -> ThreadingHTTPServer:
    pasta = pasta_hud.resolve()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def _responder(self, codigo: int, corpo: dict | None = None) -> None:
            dados = json.dumps(corpo or {"ok": codigo < 400}, ensure_ascii=False).encode()
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def _arquivo(self) -> None:
            relativo = self.path.split("?", 1)[0].lstrip("/") or "index.html"
            alvo = (pasta / relativo).resolve()
            if not alvo.is_relative_to(pasta) or not alvo.is_file():
                self._responder(404, {"erro": "não encontrado"})
                return
            conteudo = alvo.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", TIPOS.get(alvo.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(conteudo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(conteudo)

        def _sse(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            fila = cerebro.conectar()
            try:
                while True:
                    try:
                        evento = fila.get(timeout=15)
                        bloco = f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"
                    except queue.Empty:
                        bloco = ": ping\n\n"
                    self.wfile.write(bloco.encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                cerebro.desconectar(fila)
                self.close_connection = True

        def do_GET(self):
            if self.path.split("?", 1)[0] == "/api/eventos":
                self._sse()
            else:
                self._arquivo()

        def do_POST(self):
            proprio = f"http://127.0.0.1:{self.server.server_address[1]}"
            origem = self.headers.get("Origin")
            if origem and origem != proprio:
                self._responder(403, {"erro": "origem não permitida"})
                return
            if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
                self._responder(415, {"erro": "use application/json"})
                return
            try:
                corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                if not isinstance(corpo, dict):
                    raise ValueError
            except ValueError:
                self._responder(400, {"erro": "JSON inválido"})
                return
            rota = self.path.split("?", 1)[0]
            if rota == "/api/mensagem":
                cerebro.mensagem_usuario(str(corpo.get("texto") or ""), falada=False)
                self._responder(202)
            elif rota == "/api/super-j":
                cerebro.super_j()
                self._responder(200)
            elif rota == "/api/mudo":
                if cerebro.definir_mudo(bool(corpo.get("ligado"))):
                    self._responder(200)
                else:
                    self._responder(503, {"erro": "servidor de voz indisponível"})
            elif rota == "/api/fechar":
                cerebro.fechar_janela()
                self._responder(200)
            elif rota == "/api/cartao":
                try:
                    cerebro.decidir_cartao(corpo.get("id"), str(corpo.get("decisao")))
                except (ValueError, TypeError) as erro:
                    self._responder(409, {"erro": str(erro)})
                    return
                self._responder(200)
            elif rota == "/api/permissao":
                aprovado = cerebro.pedir_permissao(str(corpo.get("ferramenta") or ""), corpo.get("entrada") or {})
                self._responder(200, {"aprovado": aprovado})
            else:
                self._responder(404, {"erro": "rota desconhecida"})

    servidor = ThreadingHTTPServer(("127.0.0.1", porta), Handler)
    servidor.daemon_threads = True
    return servidor
