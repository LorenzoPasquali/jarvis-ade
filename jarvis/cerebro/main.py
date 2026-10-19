"""Cérebro do Jarvis: liga o Claude headless, a voz, a escuta, os eventos do vigia e a janela."""

import itertools
import json
import os
import queue
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import datetime

from jarvis import consultas, orca, pendencias, turno, voz_cliente
from jarvis.cerebro import escuta as escuta_mod
from jarvis.cerebro.eventos import FilaEventos
from jarvis.cerebro.fala import SeparadorFala
from jarvis.config import RAIZ, dados

ESPERA_PERMISSAO_S = 120
MAX_HISTORICO = 50
INTERVALO_SISTEMA_S = 60


def _agora() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _falar_no_servidor(texto: str) -> bool:
    return voz_cliente.chamar("/falar", {"texto": texto}) is not None


class Cerebro:
    def __init__(self, claude=None, falar: Callable[[str], bool] = _falar_no_servidor,
                 bloqueada: Callable[[], bool] = escuta_mod.tela_bloqueada, chamar_voz=voz_cliente.chamar):
        self.claude = claude
        self.bloqueada = bloqueada
        self._falar_fn = falar
        self._chamar_voz = chamar_voz
        self._ouvintes: list[queue.Queue] = []
        self._trava = threading.Lock()
        self._fila_usuario: deque[tuple[str, str]] = deque()
        self._fila_eventos = FilaEventos(dados() / "cerebro-cursor")
        self._estava_bloqueada = False
        self._resposta = ""
        self._separador = SeparadorFala(self._falar)
        self._permissoes: dict[str, dict] = {}
        self._ids_permissao = itertools.count(1)
        self._cartoes: set[int] = set()
        self._sessoes: list[dict] | None = None
        self._sistema: dict = {"tipo": "sistema", "voz": True, "orca": True}
        self._ultimo_sistema = 0.0
        self._estado = "ocioso"
        self._pendencia_no_turno = False
        self.janela_aberta = False
        self.escuta = escuta_mod.Escuta(ao_nivel=self._ao_nivel, ao_fim=self._ao_fim_escuta)

    # ---------- publicação para a janela ----------

    def publicar(self, evento: dict) -> None:
        with self._trava:
            ouvintes = list(self._ouvintes)
        for fila in ouvintes:
            fila.put(evento)

    def conectar(self) -> queue.Queue:
        fila: queue.Queue = queue.Queue()
        for evento in self.estado_inicial():
            fila.put(evento)
        with self._trava:
            self._ouvintes.append(fila)
        return fila

    def desconectar(self, fila: queue.Queue) -> None:
        with self._trava:
            if fila in self._ouvintes:
                self._ouvintes.remove(fila)

    def estado_inicial(self) -> list[dict]:
        iniciais = [{"tipo": "historico", "mensagens": self._historico()},
                    {"tipo": "sessoes", "itens": self._sessoes or []}, self._sistema,
                    {"tipo": "estado", "valor": self._estado}]
        iniciais += [self._cartao_de(p) for p in pendencias.listar()]
        return iniciais

    def _definir_estado(self, valor: str) -> None:
        self._estado = valor
        self.publicar({"tipo": "estado", "valor": valor})

    # ---------- histórico ----------

    def _registrar(self, papel: str, texto: str) -> None:
        with (dados() / "conversa.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"em": _agora(), "papel": papel, "texto": texto}, ensure_ascii=False) + "\n")

    def _historico(self) -> list[dict]:
        try:
            linhas = (dados() / "conversa.jsonl").read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        mensagens = []
        for linha in linhas[-MAX_HISTORICO:]:
            try:
                m = json.loads(linha)
            except ValueError:
                continue
            mensagens.append({"papel": m["papel"], "texto": m["texto"]})
        return mensagens

    # ---------- entrada do usuário ----------

    def mensagem_usuario(self, texto: str, falada: bool) -> None:
        texto = texto.strip()
        if not texto:
            return
        self._registrar("usuario", texto)
        self.publicar({"tipo": "usuario", "texto": texto, "falada": falada})
        self._chamar_voz("/parar")
        self._para_claude(f"[voz] {texto}" if falada else texto, "voz" if falada else "texto")

    def _para_claude(self, texto: str, tipo: str) -> None:
        if self.claude.ocupado or self._fila_usuario:
            self._fila_usuario.append((texto, tipo))
        else:
            self._enviar_claude(texto, tipo)

    def _enviar_claude(self, texto: str, tipo: str) -> None:
        turno.registrar(tipo)
        self._resposta = ""
        self._pendencia_no_turno = False
        self._separador.reiniciar()
        self._definir_estado("pensando")
        self.claude.enviar(texto)

    def super_j(self) -> None:
        self.janela_aberta = True
        if self.escuta.ativa:
            self.escuta.encerrar()
        else:
            self.escuta.iniciar()
            self._definir_estado("ouvindo")

    def fechar_janela(self) -> None:
        self.janela_aberta = False

    def _ao_nivel(self, nivel: float) -> None:
        self.publicar({"tipo": "nivel", "valor": round(nivel, 4)})

    def _ao_fim_escuta(self, texto: str | None) -> None:
        if texto:
            self.mensagem_usuario(texto, falada=True)
        elif not self.claude.ocupado:
            self._definir_estado("ocioso")

    # ---------- saída do Claude ----------

    def _falar(self, texto: str) -> None:
        if not self.janela_aberta:
            self.publicar({"tipo": "aviso", "texto": texto})
        self._definir_estado("falando")
        if not self._falar_fn(texto):
            self._sistema = {**self._sistema, "voz": False}
            self.publicar(self._sistema)

    def ao_evento_claude(self, evento: dict) -> None:
        tipo = evento.get("type")
        if tipo == "stream_event":
            interno = evento.get("event") or {}
            if interno.get("type") == "message_start" and self._resposta and not self._resposta.endswith("\n"):
                self._acrescentar("\n")
            delta = interno.get("delta") or {}
            if interno.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
                self._acrescentar(delta.get("text", ""))
        elif tipo == "result":
            turno.encerrar()
            texto = evento.get("result") or self._resposta
            self._separador.fim(texto)
            if texto.strip():
                self._registrar("jarvis", texto)
            self.publicar({"tipo": "resposta_fim", "texto": texto})
            if self._estado != "ouvindo":
                self._definir_estado("ocioso")
            if self._pendencia_no_turno and self.janela_aberta:
                threading.Thread(target=self._reabrir_escuta, daemon=True).start()
        elif tipo == "jarvis_reiniciando":
            self._definir_estado("desconectado")
        elif tipo == "system" and evento.get("subtype") == "init" and self._estado == "desconectado":
            self._definir_estado("ocioso")

    def _acrescentar(self, texto: str) -> None:
        self._resposta += texto
        self.publicar({"tipo": "delta", "texto": texto})
        self._separador.alimentar(texto)

    def _reabrir_escuta(self) -> None:
        """Depois de uma pergunta de confirmação, ouve o "sim"/"não" assim que a voz terminar."""
        fim = time.time() + 30
        while time.time() < fim:
            saude = self._chamar_voz("/saude")
            if not saude or (not saude.get("falando") and not saude.get("fila")):
                break
            time.sleep(0.3)
        if self.janela_aberta and not self.escuta.ativa and not self.claude.ocupado:
            self.escuta.iniciar()
            self._definir_estado("ouvindo")

    # ---------- confirmações ----------

    @staticmethod
    def _cartao_de(p: dict) -> dict:
        return {"tipo": "cartao", "id": p["id"], "tipo_pendencia": p["tipo"], "descricao": p["descricao"]}

    def _publicar_pendencias(self) -> None:
        abertas = {p["id"]: p for p in pendencias.listar()}
        for id_, p in abertas.items():
            if id_ not in self._cartoes:
                self._cartoes.add(id_)
                self._pendencia_no_turno = True
                self.publicar(self._cartao_de(p))
        for id_ in list(self._cartoes - abertas.keys()):
            self._cartoes.discard(id_)
            self.publicar({"tipo": "cartao_fim", "id": id_, "estado": "fechada"})

    def decidir_cartao(self, id_, decisao: str) -> None:
        if isinstance(id_, str) and id_ in self._permissoes:
            pedido = self._permissoes[id_]
            pedido["aprovado"] = decisao == "aprovar"
            pedido["pronto"].set()
            return
        id_ = int(id_)
        p = pendencias.confirmar(id_) if decisao == "aprovar" else pendencias.recusar(id_)
        self._cartoes.discard(id_)
        self.publicar({"tipo": "cartao_fim", "id": id_, "estado": p["estado"]})
        verbo = "aprovou" if decisao == "aprovar" else "recusou"
        self._para_claude(f"[sistema] O senhor {verbo} pela janela a pendência {id_} ({p['descricao']}). "
                          f"Resultado: {p['resultado'] or p['estado']}.", "sistema")

    def pedir_permissao(self, ferramenta: str, entrada: dict) -> bool:
        id_ = f"perm-{next(self._ids_permissao)}"
        pedido = {"pronto": threading.Event(), "aprovado": False}
        self._permissoes[id_] = pedido
        resumo = json.dumps(entrada, ensure_ascii=False)
        resumo = resumo if len(resumo) <= 160 else resumo[:157] + "…"
        self.publicar({"tipo": "cartao", "id": id_, "tipo_pendencia": "permissao",
                       "descricao": f"O Jarvis quer usar **{ferramenta}**: {resumo}"})
        pedido["pronto"].wait(ESPERA_PERMISSAO_S)
        del self._permissoes[id_]
        self.publicar({"tipo": "cartao_fim", "id": id_, "estado": "aprovada" if pedido["aprovado"] else "recusada"})
        return pedido["aprovado"]

    # ---------- painel e sistema ----------

    def _atualizar_sessoes(self) -> None:
        try:
            bruto = json.loads((dados() / "vigia-estado.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return
        itens = [{"projeto": a["projeto"], "worktree": a["worktree"], "estado": a["estado"],
                  "rotulo": consultas.ESTADOS.get(a["estado"], a["estado"]),
                  "mensagem": " ".join((a.get("ultima_mensagem") or "").split())[:120],
                  "desde_ms": a.get("estado_desde_ms")}
                 for a in bruto.get("agentes", {}).values()]
        if itens != self._sessoes:
            self._sessoes = itens
            self.publicar({"tipo": "sessoes", "itens": itens})
        orca_ok = bool(bruto.get("orca_ok", True))
        if orca_ok != self._sistema.get("orca"):
            self._sistema = {**self._sistema, "orca": orca_ok}
            self.publicar(self._sistema)

    def _atualizar_sistema(self) -> None:
        voz_ok = self._chamar_voz("/saude") is not None
        try:
            clima = consultas.clima_curto(consultas.buscar_clima(timeout=5))
        except Exception:
            clima = self._sistema.get("clima", "")
        novo = {**self._sistema, "voz": voz_ok, "clima": clima}
        if novo != self._sistema:
            self._sistema = novo
            self.publicar(novo)

    # ---------- laço ----------

    def laco_uma_vez(self) -> None:
        self._atualizar_sessoes()
        self._publicar_pendencias()
        self._fila_eventos.coletar()
        if self.bloqueada():
            self._estava_bloqueada = True
            return
        if self.claude.ocupado:
            return
        if self._estava_bloqueada:
            self._estava_bloqueada = False
            if not self._fila_eventos.vazia:
                linhas = "\n".join(self._fila_eventos.retirar())
                self._enviar_claude("[sistema] O senhor voltou. Resuma em uma fala curta o que aconteceu "
                                    f"enquanto esteve fora:\n{linhas}", "sistema")
                return
        if self._fila_usuario:
            self._enviar_claude(*self._fila_usuario.popleft())
        elif not self._fila_eventos.vazia:
            self._enviar_claude("[eventos]\n" + "\n".join(self._fila_eventos.retirar()), "eventos")

    def laco(self) -> None:
        while True:
            try:
                if time.time() - self._ultimo_sistema >= INTERVALO_SISTEMA_S:
                    self._ultimo_sistema = time.time()
                    threading.Thread(target=self._atualizar_sistema, daemon=True).start()
                self.laco_uma_vez()
            except Exception as erro:  # o cérebro não pode morrer por um erro isolado
                print(f"cérebro: {erro!r}", flush=True)
            time.sleep(1)


def garantir_orca() -> None:
    try:
        estado = orca.executar(["status"], timeout=10)
        if estado.get("app", {}).get("running"):
            return
    except orca.OrcaErro:
        pass
    try:
        subprocess.Popen([orca.orca_cli(), "open"], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def main() -> int:
    from jarvis.cerebro.claude import ProcessoClaude, comando_claude
    from jarvis.cerebro.servidor import criar

    env = {**os.environ, "PATH": f"{RAIZ / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}", "JARVIS_CEREBRO": "1"}
    cerebro = Cerebro()
    cerebro.claude = ProcessoClaude(comando_claude(RAIZ, os.environ.get("JARVIS_MODELO", "sonnet")),
                                    RAIZ / "sessao", env, cerebro.ao_evento_claude, dados() / "cerebro-sessao.json")
    servidor = criar(cerebro, porta=8766)  # primeiro a porta: a janela do login já pode conectar
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    garantir_orca()
    cerebro.claude.iniciar()
    print("cérebro pronto em 127.0.0.1:8766", flush=True)
    cerebro.laco()
    return 0
