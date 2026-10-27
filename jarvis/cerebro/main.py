"""Cérebro do Jarvis: liga os modelos, a voz, a escuta, os eventos do vigia e a janela."""

import itertools
import json
import os
import queue
import re
import signal
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from jarvis import consultas, local, orca, pendencias, projetos, turno, voz_cliente
from jarvis.cerebro import escuta as escuta_mod
from jarvis.cerebro import reserva
from jarvis.cerebro.eventos import FilaEventos
from jarvis.cerebro.fala import SeparadorFala
from jarvis.config import RAIZ, dados, frase_pronta

ESPERA_PERMISSAO_S = 120
MAX_ENTRADA_PERMISSAO = 4000  # acima disso o cartão não daria para ler inteiro: nega
TRAVADO_S = 300  # turno sem saída de modelo por tanto tempo: considera travado e reinicia
TRAVADO_RESERVA_S = 90  # Gemini/Codex mudos por tanto tempo: desiste deles (o Codex fica minutos reconectando)
ESPERA_LIMITE_S = 1800  # limite do Claude sem horário de volta na mensagem: tenta de novo em 30 min
MAX_ATENDIDO_NA_RESERVA = 12
NOMES = {"claude": "Claude", "gemini": "Gemini", "codex": "Codex"}
INTERVALO_PALAVRA_S = 3.0  # "Jarvis" repetido nesse intervalo conta uma vez só
_ERROS_DE_REDE = ("eai_again", "enotfound", "econnrefused", "etimedout", "getaddrinfo", "can't reach",
                  "check your internet", "network error")
_HORA = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap]m)", re.IGNORECASE)
PAUSA_APOS_ERRO_S = 600
MAX_HISTORICO = 50
INTERVALO_SISTEMA_S = 60
INTERVALO_CLIMA_S = 900  # o clima muda devagar: uma consulta a cada 15 min basta


def tipo_de_erro(texto: str) -> str:
    t = texto.casefold()
    if any(p in t for p in _ERROS_DE_REDE):
        return "rede"
    if "limit" in t or "quota" in t or "resets" in t:
        return "limite"
    return "outro"


def volta_do_limite(texto: str, agora: datetime) -> float:
    """"You've hit your session limit · resets 11:10pm (...)" -> quando tentar o Claude de novo."""
    _, achou, resto = texto.partition("resets")
    m = _HORA.search(resto) if achou else None
    if not m:
        return agora.timestamp() + ESPERA_LIMITE_S
    hora, minuto = int(m[1]) % 12 + (12 if m[3].lower() == "pm" else 0), int(m[2] or 0)
    if minuto > 59:
        return agora.timestamp() + ESPERA_LIMITE_S
    alvo = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
    if alvo <= agora:
        alvo += timedelta(days=1)
    return alvo.timestamp() + 60


_PROGRESSO_COMANDOS = (
    ("jarvis projeto", "Consultando os projetos…"),
    ("jarvis status", "Vendo as sessões abertas no Orca…"),
    ("jarvis historico", "Levantando o histórico dos projetos…"),
    ("jarvis clima", "Vendo o clima…"),
    ("jarvis enviar", "Preparando o envio ao agente…"),
    ("jarvis lancar", "Preparando a tarefa do agente…"),
    ("jarvis pendencias", "Vendo as pendências…"),
    ("orca terminal read", "Lendo o terminal do agente…"),
    ("orca search", "Buscando nas conversas dos agentes…"),
)


def descrever_ferramenta(nome: str, entrada: dict) -> str:
    """Uma linha para a janela enquanto o modelo trabalha (só texto: a voz fica para a resposta)."""
    if nome == "Bash":
        comando = " ".join(str(entrada.get("command") or "").split())
        for prefixo, texto in _PROGRESSO_COMANDOS:
            if comando.startswith(prefixo):
                return texto
        return f"Rodando: {comando[:70]}"
    if nome == "WebSearch":
        return f"Pesquisando na web: {str(entrada.get('query') or '')[:80]}"
    if nome == "WebFetch":
        return "Lendo uma página da web…"
    if nome in ("Read", "Grep", "Glob"):
        return "Lendo arquivos dos projetos…"
    if nome in ("Task", "Agent"):
        return "Delegando parte do trabalho…"
    return f"Usando {nome}…"


def _agora() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _falar_no_servidor(texto: str) -> bool:
    return voz_cliente.chamar("/falar", {"texto": texto}) is not None


class Cerebro:
    def __init__(self, claude=None, falar: Callable[[str], bool] = _falar_no_servidor,
                 bloqueada: Callable[[], bool] = escuta_mod.tela_bloqueada, chamar_voz=voz_cliente.chamar,
                 codex=None, gemini=None):
        self.claude, self.gemini, self.codex = claude, gemini, codex
        self.bloqueada = bloqueada
        self._falar_fn = falar
        self._chamar_voz = chamar_voz
        self._ouvintes: list[queue.Queue] = []
        self._trava = threading.Lock()
        self._despacho = threading.RLock()  # um turno de cada vez: entrada, laço e fim de resposta
        self._fila_usuario: deque[tuple[str, str]] = deque()
        self._fila_eventos = FilaEventos(dados() / "cerebro-cursor")
        self._estava_bloqueada = False
        self._resposta = ""
        self._separador = SeparadorFala(self._falar)
        self._permissoes: dict[str, dict] = {}
        self._ids_permissao = itertools.count(1)
        self._cartoes: set[int] = set()
        self._sessoes: list[dict] | None = None
        self._projetos: list[projetos.Projeto] = []
        self._sistema: dict = {"tipo": "sistema", "voz": True, "orca": True, "modelo": "Claude", "mudo": False}
        self._ultimo_sistema = 0.0
        self._ultimo_clima = 0.0
        self._estado = "ocioso"
        self._pendencia_no_turno = False
        self._calar_turno = False  # o senhor falou por cima: o resto desta resposta não é falado
        self._ultima_saida = time.time()
        self._eventos_pausados_ate = 0.0
        self._entrada_atual: tuple[str, str] | None = None
        self._provedor_ativo = "claude"
        self._fallback_ativo = False
        self._claude_volta_em = 0.0  # limite de uso: até lá os turnos vão direto ao modo reserva
        self._atendido_na_reserva: list[dict] = []  # o que o Claude ainda não sabe que foi conversado
        self._ultima_palavra = 0.0
        self._fala_atual = ""
        self.ouvido = None
        self.mostrar_janela: Callable[[], None] = _mostrar_janela
        self.tocar: Callable[[Path], None] = _tocar
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
        if self._ocupado():
            self._calar_turno = True
        self._para_claude(f"[voz] {texto}" if falada else texto, "voz" if falada else "texto")

    def _para_claude(self, texto: str, tipo: str) -> None:
        with self._despacho:
            if self._ocupado() or self._fila_usuario:
                self._fila_usuario.append((texto, tipo))
            else:
                self._enviar_claude(texto, tipo)

    def _enviar_claude(self, texto: str, tipo: str) -> None:
        turno.registrar(tipo)
        self._calar_turno = False
        self._ultima_saida = time.time()
        self._resposta = ""
        self._pendencia_no_turno = False
        self._separador.reiniciar()
        self._entrada_atual = (texto, tipo)
        self._provedor_ativo = "claude"
        self._fallback_ativo = False
        self._definir_estado("pensando")
        if time.time() < self._claude_volta_em and self._iniciar_fallback(
                "Claude", {"result": f"no limite até {datetime.fromtimestamp(self._claude_volta_em):%H:%M}"}):
            return
        self._mostrar_modelo("claude")
        if self._atendido_na_reserva:
            texto = ("[contexto] Enquanto você esteve indisponível, o modo reserva (Gemini/Codex) atendeu o senhor:\n"
                     f"{reserva.conversa(self._atendido_na_reserva)}\n[fim do contexto]\n\n{texto}")
        self.claude.enviar(texto)

    def _mostrar_modelo(self, provedor: str) -> None:
        nome = NOMES.get(provedor, provedor)
        if self._sistema.get("modelo") != nome:
            self._sistema = {**self._sistema, "modelo": nome}
            self.publicar(self._sistema)

    def palavra_jarvis(self, resto: str = "") -> float | None:
        """O senhor disse "Jarvis" (`resto`: o que veio depois, na mesma frase). Chamado pelo ouvido.

        A janela abre (ou volta à vista padrão, com o chat recolhido) na hora, já ouvindo.
        "Jarvis, <pergunta>": a pergunta vai direto. Só "Jarvis": cala a fala; com a janela fechada, cumprimenta
        com a frase já gerada. Devolve None (o ouvido não espera pergunta) ou o instante a partir do qual o áudio já
        é do senhor (fim da saudação; 0.0 = logo depois do "Jarvis"): o próprio ouvido pega a pergunta.
        """
        agora = time.time()
        if self.escuta.ativa or self.bloqueada() or agora - self._ultima_palavra < INTERVALO_PALAVRA_S:
            return None
        if self._estado == "falando" and "jarvis" in self._fala_atual.casefold():
            return None  # quem disse "Jarvis" foi a própria fala dele, não o senhor
        self._ultima_palavra = agora
        self._chamar_voz("/parar")
        janela_estava_aberta = self.janela_aberta
        if not janela_estava_aberta:
            self.mostrar_janela()
            self.janela_aberta = True
        self.publicar({"tipo": "chamado"})  # a janela recolhe o chat e mostra o núcleo
        if resto:
            self.mensagem_usuario(resto, falada=True)
            return None
        self._definir_estado("ouvindo")
        if janela_estava_aberta:
            return 0.0
        saudacao = frase_pronta("saudacao")
        saude = self._chamar_voz("/saude") or {}
        if saudacao.exists() and not saude.get("mudo"):
            self.tocar(saudacao)
        return time.time()  # o que vier depois da saudação já é a pergunta

    def pergunta_ouvida(self, texto: str | None) -> None:
        """A pergunta que o ouvido pegou depois do "Jarvis" (None: o senhor não disse nada)."""
        if texto:
            self.mensagem_usuario(texto, falada=True)
        elif not self.escuta.ativa and self._estado == "ouvindo":
            self._definir_estado("pensando" if self._ocupado() else "ocioso")

    def super_j(self) -> None:
        self.janela_aberta = True
        if not self.escuta.ativa:
            if self._ocupado():
                self._calar_turno = True  # o senhor quer falar: o resto da resposta em andamento fica só no texto
            self._definir_estado("ouvindo")
            self.escuta.iniciar()

    def fechar_janela(self) -> None:
        """Esc ou ×: para de ouvir na hora; só volta com "Jarvis" ou Super+J."""
        self.janela_aberta = False
        if self.escuta.ativa:
            self.escuta.cancelar()
        if self.ouvido is not None:
            self.ouvido.cancelar_espera()
        if self._estado == "ouvindo":
            self._definir_estado("pensando" if self._ocupado() else "ocioso")

    def definir_mudo(self, ligado: bool) -> bool:
        """Botão de voz da janela (ou `jarvis mudo on|off`): repassa ao servidor de voz e atualiza as janelas."""
        resposta = self._chamar_voz("/mudo", {"ligado": ligado})
        if resposta is None:
            return False
        self._sistema = {**self._sistema, "mudo": bool(resposta.get("mudo", ligado))}
        self.publicar(self._sistema)
        return True

    def _ao_nivel(self, nivel: float) -> None:
        self.publicar({"tipo": "nivel", "valor": round(nivel, 4)})

    def _ao_fim_escuta(self, texto: str | None) -> None:
        if texto:
            self.mensagem_usuario(texto, falada=True)
        else:
            self._definir_estado("pensando" if self._ocupado() else "ocioso")

    # ---------- saída do Claude ----------

    def _falar(self, texto: str) -> None:
        if self._calar_turno:
            return
        self._fala_atual = texto
        if not self.janela_aberta:
            self.publicar({"tipo": "aviso", "texto": texto})
        self._definir_estado("falando")
        if not self._falar_fn(texto):
            self._sistema = {**self._sistema, "voz": False}
            self.publicar(self._sistema)

    def _ocupado(self) -> bool:
        return (bool(self.claude and self.claude.ocupado) or bool(self.gemini and self.gemini.ocupado)
                or bool(self.codex and self.codex.ocupado))

    def ao_evento_claude(self, evento: dict) -> None:
        self._ao_evento_modelo(evento, "Claude")

    def ao_evento_codex(self, evento: dict) -> None:
        self._ao_evento_modelo(evento, "Codex")

    def ao_evento_gemini(self, evento: dict) -> None:
        self._ao_evento_modelo(evento, "Gemini")

    def _iniciar_fallback(self, provedor: str, evento: dict) -> bool:
        if not self._entrada_atual:
            return False
        if provedor == "Claude":
            destino, processo = ("gemini", self.gemini) if self.gemini else ("codex", self.codex)
        elif provedor == "Gemini":
            destino, processo = "codex", self.codex
        else:
            return False
        if not processo:
            return False
        detalhe = str(evento.get("result") or "")[:300]
        print(f"cérebro: {provedor} indisponível ({detalhe!r}); tentando {destino}", flush=True)
        self._fallback_ativo = True
        self._provedor_ativo = destino
        self._mostrar_modelo(destino)
        self._resposta = ""
        self._chamar_voz("/parar")
        self._separador.reiniciar()
        self.publicar({"tipo": "resposta_fim", "texto": ""})
        self._definir_estado("pensando")
        historico = self._historico()
        if self._entrada_atual[1] in ("voz", "texto") and historico and historico[-1]["papel"] == "usuario":
            historico = historico[:-1]  # a mensagem atual já vai no fim
        resumo = projetos.formatar_lista(self._projetos, time.time()) if self._projetos else ""
        processo.enviar(reserva.mensagem(self._entrada_atual[0], historico, projetos=resumo))
        return True

    def _tentar_reserva(self, provedor: str, evento: dict) -> bool:
        erro = str(evento.get("result") or "")
        tipo = tipo_de_erro(erro)
        if tipo == "rede":  # sem internet o Gemini e o Codex também falham: avisa logo, sem cascata de minutos
            return False
        if provedor == "Claude" and tipo == "limite":
            self._claude_volta_em = volta_do_limite(erro, datetime.now().astimezone())
            print(f"cérebro: Claude no limite; modo reserva até "
                  f"{datetime.fromtimestamp(self._claude_volta_em):%H:%M}", flush=True)
        return self._iniciar_fallback(provedor, evento)

    def _ao_evento_modelo(self, evento: dict, provedor: str) -> None:
        tipo = evento.get("type")
        if self._entrada_atual and provedor.lower() != self._provedor_ativo:
            return  # descarta eventos atrasados de um provedor que já foi substituído
        self._ultima_saida = time.time()
        if tipo == "stream_event":
            interno = evento.get("event") or {}
            if interno.get("type") == "message_start" and self._resposta and not self._resposta.endswith("\n"):
                self._acrescentar("\n")
            delta = interno.get("delta") or {}
            if interno.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
                self._acrescentar(delta.get("text", ""))
        elif tipo == "assistant":
            for bloco in (evento.get("message") or {}).get("content") or []:
                if isinstance(bloco, dict) and bloco.get("type") == "tool_use":
                    self.publicar({"tipo": "progresso",
                                   "texto": descrever_ferramenta(bloco.get("name") or "", bloco.get("input") or {})})
        elif tipo == "result":
            with self._despacho:
                if evento.get("is_error") and self._tentar_reserva(provedor, evento):
                    return
                self._fim_do_turno(evento, provedor)
        elif tipo == "jarvis_reiniciando":
            self._definir_estado("desconectado")
        elif tipo in ("system", "jarvis_pronto") and self._estado == "desconectado":
            self._definir_estado("ocioso")

    def _fim_do_turno(self, evento: dict, provedor: str = "Claude") -> None:
        if evento.get("is_error"):
            turno.encerrar()
            self._erro_do_modelo(evento, provedor)
            return
        texto = evento.get("result") or self._resposta
        if (not texto.strip() and self._entrada_atual
                and self._entrada_atual[1] in ("voz", "texto")):
            vazio = {**evento, "is_error": True,
                     "result": f"{provedor} encerrou o turno sem fornecer uma resposta."}
            if self._iniciar_fallback(provedor, vazio):
                return
            turno.encerrar()
            self._erro_do_modelo(vazio, provedor)
            return
        turno.encerrar()
        self._separador.fim(texto)
        self._lembrar_para_o_claude(texto)
        if texto.strip():
            self._registrar("jarvis", texto)
        self.publicar({"tipo": "resposta_fim", "texto": texto})
        if self._estado != "ouvindo":
            self._definir_estado("ocioso")
        if self._pendencia_no_turno and self.janela_aberta:
            threading.Thread(target=self._reabrir_escuta, daemon=True).start()
        self._fallback_ativo = False
        self._entrada_atual = None

    def _lembrar_para_o_claude(self, resposta: str) -> None:
        if self._provedor_ativo == "claude":
            self._atendido_na_reserva = []  # o Claude respondeu: já recebeu o contexto
            return
        texto, tipo = self._entrada_atual or ("", "")
        if tipo in ("voz", "texto"):
            self._atendido_na_reserva.append({"papel": "usuario", "texto": texto})
        if resposta.strip():
            self._atendido_na_reserva.append({"papel": "jarvis", "texto": resposta})
        self._atendido_na_reserva = self._atendido_na_reserva[-MAX_ATENDIDO_NA_RESERVA:]

    def _erro_do_modelo(self, evento: dict, provedor: str) -> None:
        """Erros de modelo viram uma frase curta em português — nunca lidos crus."""
        print(f"cérebro: erro do {provedor}: {evento.get('subtype')} {str(evento.get('result'))[:300]!r}", flush=True)
        self._separador.reiniciar()
        if evento.get("subtype") == "error_restart":
            texto, fala = (f"Perdi a conexão com o {provedor} no meio da resposta, senhor. Pode repetir, por favor?",
                           "Perdi a conexão, senhor. Pode repetir?")
        elif tipo_de_erro(str(evento.get("result") or "")) == "rede":
            self._eventos_pausados_ate = time.time() + PAUSA_APOS_ERRO_S
            texto, fala = ("Estou sem conexão com a internet agora, senhor, e nenhum modelo responde assim. "
                           "Tente de novo quando a rede voltar.",
                           "Estou sem internet agora, senhor.")
        else:
            self._eventos_pausados_ate = time.time() + PAUSA_APOS_ERRO_S
            texto, fala = (f"Não consegui responder agora, senhor: o {provedor} devolveu um erro (talvez limite de uso). "
                           "Os avisos automáticos ficam pausados por dez minutos.",
                           "Não consegui responder agora, senhor.")
        self._registrar("jarvis", texto)
        self.publicar({"tipo": "resposta_fim", "texto": texto})
        self._falar(fala)
        self._definir_estado("desconectado" if evento.get("subtype") == "error_restart" else "ocioso")
        self._fallback_ativo = False
        self._entrada_atual = None

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
        if self.janela_aberta and not self.escuta.ativa and not self._ocupado():
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
        fechadas = self._cartoes - abertas.keys()
        if fechadas:
            estados = {p["id"]: p for p in pendencias.listar(apenas_abertas=False)}
            for id_ in fechadas:
                self._cartoes.discard(id_)
                p = estados.get(id_, {"estado": "fechada", "descricao": ""})
                self.publicar({"tipo": "cartao_fim", "id": id_, "estado": p["estado"]})
                if p["estado"] == "expirada":
                    aviso = "A confirmação expirou sem resposta, senhor. Nada foi feito."
                    self._registrar("jarvis", f"{aviso} ({p['descricao']})")
                    self._falar(aviso)

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
        detalhe = json.dumps(entrada, ensure_ascii=False, indent=1)
        if len(detalhe) > MAX_ENTRADA_PERMISSAO:
            return False  # o senhor não conseguiria ler tudo o que aprovaria
        id_ = f"perm-{next(self._ids_permissao)}"
        pedido = {"pronto": threading.Event(), "aprovado": False}
        self._permissoes[id_] = pedido
        self.publicar({"tipo": "cartao", "id": id_, "tipo_pendencia": "permissao",
                       "descricao": f"O Jarvis quer usar **{ferramenta}**:", "detalhe": detalhe})
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
        saude = self._chamar_voz("/saude")
        novo = {**self._sistema, "voz": saude is not None}
        if saude is not None:
            novo["mudo"] = bool(saude.get("mudo"))
        if time.time() - self._ultimo_clima >= INTERVALO_CLIMA_S:
            lugar = local.atual()
            novo.update(cidade=lugar.cidade, fuso=lugar.fuso)
            try:
                novo["clima"] = consultas.clima_curto(consultas.buscar_clima(lugar.latitude, lugar.longitude,
                                                                               timeout=5), lugar.cidade)
                self._ultimo_clima = time.time()
            except Exception:
                pass  # fica o último clima; tenta de novo no próximo minuto
        if novo != self._sistema:
            self._sistema = novo
            self.publicar(novo)
        self._atualizar_projetos()

    def _atualizar_projetos(self) -> None:
        """Lista guardada para o modo reserva (o Claude usa `jarvis projetos` quando precisa)."""
        try:
            self._projetos = projetos.listar()
        except Exception as erro:  # Orca fechado ou histórico ilegível: fica a última lista boa
            print(f"cérebro: não consegui listar os projetos: {erro!r}", flush=True)

    # ---------- laço ----------

    def laco_uma_vez(self) -> None:
        self._atualizar_sessoes()
        self._publicar_pendencias()
        self._fila_eventos.coletar()
        with self._despacho:
            self._despachar()

    def _despachar(self) -> None:
        if self.bloqueada():
            self._estava_bloqueada = True
            return
        limite = TRAVADO_S if self._provedor_ativo == "claude" else TRAVADO_RESERVA_S
        if self._ocupado() and time.time() - self._ultima_saida >= limite:
            print("cérebro: modelo sem resposta há muito tempo; reiniciando", flush=True)
            self._ultima_saida = time.time()
            processo = {"claude": self.claude, "gemini": self.gemini, "codex": self.codex}.get(
                self._provedor_ativo)
            if processo:
                processo.reiniciar()
            return
        if self._ocupado() or self.escuta.ativa:  # não começa turno com o senhor falando
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
        elif not self._fila_eventos.vazia and time.time() >= self._eventos_pausados_ate:
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


def _tocar(arquivo: Path) -> None:
    try:
        subprocess.run(["pw-play", str(arquivo)], timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _mostrar_janela() -> None:
    from jarvis import hud_cli

    pid = hud_cli._pid()
    if pid and hud_cli._janela_viva(pid):
        os.kill(pid, signal.SIGUSR1)


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
    from jarvis.cerebro.codex import ProcessoCodex, comando_codex
    from jarvis.cerebro.gemini import ProcessoGemini, comando_gemini
    from jarvis.cerebro.ouvido import Ouvido
    from jarvis.cerebro.servidor import criar

    env = {**os.environ, "PATH": f"{RAIZ / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}", "JARVIS_CEREBRO": "1"}
    cerebro = Cerebro()
    cerebro.claude = ProcessoClaude(comando_claude(RAIZ, os.environ.get("JARVIS_MODELO", "haiku")),
                                    RAIZ / "sessao", env, cerebro.ao_evento_claude, dados() / "cerebro-sessao.json")
    cerebro.gemini = ProcessoGemini(comando_gemini(os.environ.get("JARVIS_GEMINI_MODELO", "gemini-3.8-flash-medium")),
                                    RAIZ, env, cerebro.ao_evento_gemini, dados() / "gemini-sessao.json",
                                    RAIZ / "sessao/CLAUDE.md")
    cerebro.codex = ProcessoCodex(comando_codex(os.environ.get("JARVIS_CODEX_MODELO")), RAIZ / "sessao", env,
                                  cerebro.ao_evento_codex, dados() / "codex-sessao.json", RAIZ / "sessao/CLAUDE.md")
    servidor = criar(cerebro, porta=8766)  # primeiro a porta: a janela do login já pode conectar
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    garantir_orca()
    cerebro.claude.iniciar()
    cerebro.ouvido = Ouvido(cerebro.palavra_jarvis, ao_perguntar=cerebro.pergunta_ouvida, ao_nivel=cerebro._ao_nivel,
                            pausado=lambda: cerebro.escuta.ativa or cerebro.bloqueada())
    cerebro.ouvido.iniciar()
    print("cérebro pronto em 127.0.0.1:8766", flush=True)
    cerebro.laco()
    return 0
