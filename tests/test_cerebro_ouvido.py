import array
import math

import pytest

from jarvis.cerebro import main as cerebro_main
from jarvis.cerebro import ouvido as ouvido_mod
from jarvis.cerebro.main import Cerebro
from jarvis.cerebro.ouvido import BYTES_BLOCO, Recortador, depois_de_jarvis
from jarvis.config import frase_pronta


def esperar(cond, limite=5.0):
    import time
    fim = time.time() + limite
    while time.time() < fim:
        if cond():
            return True
        time.sleep(0.02)
    return False


def bloco(nivel: float) -> bytes:
    n = BYTES_BLOCO // 2
    return array.array("h", (int(nivel * 32767 * math.sin(i / 3)) for i in range(n))).tobytes()


SILENCIO, FALA = bloco(0.002), bloco(0.1)


@pytest.mark.parametrize("texto, resto", [
    ("Jarvis.", ""),
    ("Jarvis, como está o app de saúde?", "como está o app de saúde?"),
    ("Ei, Járvis, bom dia", "bom dia"),
    ("Ok jarves que horas são", "que horas são"),
    ("Djarvis!", ""),
    ("Bom dia, tudo bem?", None),
    ("O Jarbas chegou", None),
    ("Falei com o pessoal do Jarvis ontem", None),  # "Jarvis" no meio da frase não chama
    ("", None),
])
def test_depois_de_jarvis(texto, resto):
    assert depois_de_jarvis(texto) == resto


def test_recortador_entrega_a_frase_com_um_pouco_de_antes():
    r = Recortador(silencio_s=0.3)
    saidas = [r.alimentar(b) for b in [SILENCIO] * 20 + [FALA] * 6 + [SILENCIO] * 3]
    frases = [f for f in saidas if f]
    assert len(frases) == 1
    assert frases[0].startswith(SILENCIO * 3)  # 300 ms de antes, para não cortar o "Jar"
    assert FALA * 6 in frases[0]


def test_recortador_ignora_estalo_e_falatorio_comprido():
    r = Recortador(silencio_s=0.3, maximo_s=2.0)
    estalo = [SILENCIO] * 20 + [FALA] + [SILENCIO] * 5
    longo = [FALA] * 30 + [SILENCIO] * 5
    assert not any(r.alimentar(b) for b in estalo + longo)
    depois = [r.alimentar(b) for b in [FALA] * 6 + [SILENCIO] * 3]
    assert any(depois)  # depois do descarte, volta a recortar normalmente


class Relogio:
    def __init__(self):
        self.t = 1000.0

    def blocos(self, o, recortador, blocos):
        for b in blocos:
            self.t += 0.1
            o.processar(recortador, b, self.t)


def _modo_pergunta(transcricoes, desde_saudacao=None):
    """Ouvido com transcrições roteiradas; `ao_chamar` devolve o fim da saudação (ou 0)."""
    eventos = []

    def chamar(rota, corpo=None, timeout=3.0):
        eventos.append(("transcrever", corpo.get("max_tokens")))
        return {"texto": transcricoes.pop(0)}

    def ao_chamar(resto):
        eventos.append(("chamado", resto))
        return desde_saudacao() if desde_saudacao else 0.0
    o = ouvido_mod.Ouvido(ao_chamar, ao_perguntar=lambda t: eventos.append(("pergunta", t)), chamar=chamar,
                          ao_nivel=lambda n: eventos.append(("nivel", None)))
    return o, eventos


def _rodar_conferencias(o, monkeypatch):
    """Roda `conferir` e a transcrição da pergunta na hora, sem threads."""
    class ThreadNaHora:
        def __init__(self, target, args=(), daemon=None):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)
    monkeypatch.setattr(ouvido_mod.threading, "Thread", ThreadNaHora)


def test_jarvis_sozinho_e_a_pergunta_seguinte_sem_perder_o_comeco(dados_tmp, monkeypatch):
    o, eventos = _modo_pergunta(["Jarvis.", "Como está o app de saúde?"])
    _rodar_conferencias(o, monkeypatch)
    r, relogio = Recortador(), Relogio()
    relogio.blocos(o, r, [SILENCIO] * 20 + [FALA] * 5 + [SILENCIO] * 8)  # "Jarvis" + 0,8 s
    assert ("chamado", "") in eventos and o.esperando_pergunta
    relogio.blocos(o, r, [FALA] * 15 + [SILENCIO] * 11)  # a pergunta, emendada logo depois
    assert eventos[-1] == ("pergunta", "Como está o app de saúde?")
    assert ("transcrever", None) in eventos and not o.esperando_pergunta
    assert ("nivel", None) in eventos  # o núcleo pulsa com a voz enquanto espera


def test_a_saudacao_nao_vira_pergunta(dados_tmp, monkeypatch):
    relogio = Relogio()
    fim_saudacao = []
    o, eventos = _modo_pergunta(["Jarvis.", "Que horas são?"], desde_saudacao=lambda: fim_saudacao[-1])
    _rodar_conferencias(o, monkeypatch)
    r = Recortador()
    relogio.blocos(o, r, [SILENCIO] * 20 + [FALA] * 5)
    fim_saudacao.append(relogio.t + 2.4)  # o "Jarvis" termina e a saudação toca até aqui
    relogio.blocos(o, r, [SILENCIO] * 8)
    relogio.blocos(o, r, [FALA] * 15 + [SILENCIO] * 11)  # a própria saudação, captada pelo microfone
    assert not any(e[0] == "pergunta" for e in eventos) and o.esperando_pergunta
    relogio.blocos(o, r, [FALA] * 10 + [SILENCIO] * 11)  # agora sim, o senhor
    assert eventos[-1] == ("pergunta", "Que horas são?")


def test_sem_pergunta_desiste_depois_da_espera(dados_tmp, monkeypatch):
    o, eventos = _modo_pergunta(["Jarvis."])
    _rodar_conferencias(o, monkeypatch)
    r, relogio = Recortador(), Relogio()
    relogio.blocos(o, r, [SILENCIO] * 20 + [FALA] * 5 + [SILENCIO] * 8)
    relogio.t = time_real = __import__("time").time() + ouvido_mod.ESPERA_PERGUNTA_S + 1
    relogio.blocos(o, r, [SILENCIO] * 2)
    assert eventos[-1] == ("pergunta", None) and not o.esperando_pergunta


def _ouvido(respostas, ouvidas):
    chamadas = []

    def chamar(rota, corpo=None, timeout=3.0):
        chamadas.append(corpo)
        return {"texto": respostas[len(chamadas) - 1]}
    return ouvido_mod.Ouvido(lambda resto: ouvidas.append(resto), chamar=chamar), chamadas


def test_so_jarvis_curto_nao_transcreve_de_novo(dados_tmp):
    ouvidas = []
    o, chamadas = _ouvido(["Jarvis."], ouvidas)
    o.conferir(FALA * 8)
    assert ouvidas == [""]
    assert chamadas[0]["max_tokens"] == ouvido_mod.TOKENS_CONFERIR and len(chamadas) == 1
    assert not list(dados_tmp.glob("ouvido-*.wav"))


def test_jarvis_com_pergunta_transcreve_a_frase_inteira(dados_tmp):
    ouvidas = []
    o, chamadas = _ouvido(["Jarvis, como está o", "Jarvis, como está o app de saúde?"], ouvidas)
    o.conferir(FALA * 25)
    assert ouvidas == ["como está o app de saúde?"]
    assert "max_tokens" not in chamadas[1]


def test_frase_sem_jarvis_nao_chama(dados_tmp):
    ouvidas = []
    o, chamadas = _ouvido(["Bom dia, tudo bem?"], ouvidas)
    o.conferir(FALA * 25)
    assert ouvidas == [] and len(chamadas) == 1


def test_limite_de_transcricoes_por_minuto(dados_tmp):
    ouvidas = []
    o, chamadas = _ouvido(["nada"] * 50, ouvidas)
    for _ in range(ouvido_mod.MAX_POR_MINUTO + 5):
        o.conferir(FALA * 5)
    assert len(chamadas) == ouvido_mod.MAX_POR_MINUTO


def test_ouvido_le_o_microfone_e_confere_as_frases(dados_tmp, tmp_path):
    import sys
    sinal = tmp_path / "audio.raw"
    sinal.write_bytes(SILENCIO * 20 + FALA * 6 + SILENCIO * 10)
    gravador = [sys.executable, "-c", f"import sys,time\nsys.stdout.buffer.write(open({str(sinal)!r},'rb').read())\n"
                                      "sys.stdout.flush(); time.sleep(5)"]
    ouvidas = []
    o = ouvido_mod.Ouvido(ouvidas.append, chamar=lambda rota, corpo=None, timeout=3.0: {"texto": "Jarvis"},
                          comando=gravador)
    o.iniciar()
    assert esperar(lambda: ouvidas == [""])
    o.parar()


def test_pausado_nao_confere(dados_tmp, tmp_path):
    import sys
    import time
    sinal = tmp_path / "audio.raw"
    sinal.write_bytes(SILENCIO * 20 + FALA * 6 + SILENCIO * 10)
    gravador = [sys.executable, "-c", f"import sys,time\nsys.stdout.buffer.write(open({str(sinal)!r},'rb').read())\n"
                                      "sys.stdout.flush(); time.sleep(5)"]
    chamadas = []
    o = ouvido_mod.Ouvido(lambda r: None, pausado=lambda: True, comando=gravador,
                          chamar=lambda rota, corpo=None, timeout=3.0: chamadas.append(1) or {"texto": ""})
    o.iniciar()
    time.sleep(1.0)
    o.parar()
    assert chamadas == []


def _cerebro(dados_tmp, saude=None):
    chamadas, tocadas, janelas = [], [], []

    def voz(rota, corpo=None, **_):
        chamadas.append(rota)
        return saude if rota == "/saude" else {}
    c = Cerebro(claude=None, falar=lambda t: True, bloqueada=lambda: False, chamar_voz=voz)
    c.tocar = tocadas.append
    c.mostrar_janela = lambda: janelas.append(1)
    iniciadas = []
    c.escuta.iniciar = lambda: iniciadas.append(1)
    return c, chamadas, tocadas, janelas, iniciadas


def test_jarvis_com_pergunta_vai_direto_e_abre_a_janela(dados_tmp):
    c, chamadas, tocadas, janelas, iniciadas = _cerebro(dados_tmp, saude={})
    enviadas = []
    c.mensagem_usuario = lambda texto, falada: enviadas.append((texto, falada))
    c.palavra_jarvis("como está o app de saúde?")
    assert enviadas == [("como está o app de saúde?", True)]
    assert janelas == [1] and c.janela_aberta and tocadas == [] and iniciadas == []


def test_jarvis_abre_a_janela_antes_de_cumprimentar_e_deixa_o_ouvido_pegar_a_pergunta(dados_tmp):
    saudacao = frase_pronta("saudacao")
    saudacao.parent.mkdir(parents=True, exist_ok=True)
    saudacao.write_bytes(b"RIFF")
    c, chamadas, tocadas, janelas, iniciadas = _cerebro(dados_tmp, saude={"mudo": False})
    ordem = []
    c.mostrar_janela = lambda: ordem.append("janela")
    c.tocar = lambda arquivo: ordem.append("saudacao")
    publicados = []
    c.publicar = publicados.append
    desde = c.palavra_jarvis()
    assert ordem == ["janela", "saudacao"]  # a janela aparece na hora; a voz vem depois
    assert chamadas[0] == "/parar" and desde > 0
    assert {"tipo": "chamado"} in publicados and c._estado == "ouvindo"
    assert iniciadas == []  # quem pega a pergunta é o próprio ouvido (não perde o começo)
    assert c.palavra_jarvis() is None  # eco/repetição logo em seguida: ignora
    enviadas = []
    c.mensagem_usuario = lambda texto, falada: enviadas.append(texto)
    c.pergunta_ouvida("como está o app de saúde?")
    assert enviadas == ["como está o app de saúde?"]


def test_jarvis_mudo_ou_sem_frase_pronta_nao_cumprimenta(dados_tmp):
    c, _, tocadas, janelas, _ = _cerebro(dados_tmp, saude={"mudo": True})
    frase = frase_pronta("saudacao")
    frase.parent.mkdir(parents=True, exist_ok=True)
    frase.write_bytes(b"RIFF")
    assert c.palavra_jarvis() > 0
    assert tocadas == [] and janelas == [1]
    frase.unlink()
    c2, _, tocadas2, _, _ = _cerebro(dados_tmp, saude={})
    c2.palavra_jarvis()
    assert tocadas2 == []


def test_jarvis_ignorado_quando_ja_ouve_ou_quando_a_propria_fala_disse_jarvis(dados_tmp):
    c, _, tocadas, janelas, iniciadas = _cerebro(dados_tmp, saude={})
    c.escuta.ativa = True
    assert c.palavra_jarvis() is None
    c.escuta.ativa = False
    c._estado, c._fala_atual = "falando", "Sou o Jarvis, senhor."
    assert c.palavra_jarvis() is None
    assert janelas == [] and iniciadas == []


def test_com_a_janela_aberta_jarvis_cala_e_ouve_sem_saudacao(dados_tmp):
    saudacao = frase_pronta("saudacao")
    saudacao.parent.mkdir(parents=True, exist_ok=True)
    saudacao.write_bytes(b"RIFF")
    c, chamadas, tocadas, janelas, iniciadas = _cerebro(dados_tmp, saude={"mudo": False})
    c.janela_aberta = True
    c._estado, c._fala_atual = "falando", "Os testes passaram, senhor."
    publicados = []
    c.publicar = publicados.append
    assert c.palavra_jarvis() == 0.0  # a pergunta vale logo depois do "Jarvis"
    assert chamadas[0] == "/parar" and tocadas == [] and janelas == []
    assert c._estado == "ouvindo" and {"tipo": "chamado"} in publicados


def test_sem_pergunta_volta_ao_ocioso(dados_tmp):
    c, *_ = _cerebro(dados_tmp, saude={})
    c.janela_aberta = True
    c.palavra_jarvis()
    c.pergunta_ouvida(None)
    assert c._estado == "ocioso"


def test_ferramentas_viram_progresso_em_texto(dados_tmp):
    c, *_ = _cerebro(dados_tmp, saude={})
    publicados = []
    c.publicar = publicados.append
    c.ao_evento_claude({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "Vou ver."},
        {"type": "tool_use", "name": "Bash", "input": {"command": "jarvis projetos --todos"}},
        {"type": "tool_use", "name": "WebSearch", "input": {"query": "notícias IA hoje"}},
    ]}})
    assert [p["texto"] for p in publicados if p["tipo"] == "progresso"] == [
        "Consultando os projetos…", "Pesquisando na web: notícias IA hoje"]
    assert cerebro_main.descrever_ferramenta("Bash", {"command": "ls -la /git"}) == "Rodando: ls -la /git"


def test_esc_para_de_ouvir_na_hora(dados_tmp):
    c, *_ = _cerebro(dados_tmp, saude={})
    canceladas, esperas = [], []
    c.escuta.ativa = True
    c.escuta.cancelar = lambda: canceladas.append(1)
    c.ouvido = type("O", (), {"cancelar_espera": lambda self: esperas.append(1)})()
    c._estado = "ouvindo"
    c.fechar_janela()
    assert canceladas == [1] and esperas == [1] and c._estado == "ocioso" and not c.janela_aberta


def test_whisper_repetindo_em_ruido_e_descartado():
    from jarvis.voz_cliente import transcricao_util
    assert transcricao_util("E aí " * 40, 10.0) is None
    assert transcricao_util("Não, não, não, espera: abre o portfólio primeiro", 3.0)
