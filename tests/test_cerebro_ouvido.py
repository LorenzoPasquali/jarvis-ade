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


def _ouvido(respostas, ouvidas):
    chamadas = []

    def chamar(rota, corpo=None, timeout=3.0):
        chamadas.append(corpo)
        return {"texto": respostas[len(chamadas) - 1]}
    return ouvido_mod.Ouvido(ouvidas.append, chamar=chamar), chamadas


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


def test_jarvis_cala_cumprimenta_e_abre_ouvindo(dados_tmp):
    saudacao = frase_pronta("saudacao")
    saudacao.parent.mkdir(parents=True, exist_ok=True)
    saudacao.write_bytes(b"RIFF")
    c, chamadas, tocadas, janelas, iniciadas = _cerebro(dados_tmp, saude={"mudo": False})
    c.palavra_jarvis()
    assert chamadas[0] == "/parar"
    assert tocadas == [saudacao] and janelas == [1] and iniciadas == [1]
    assert c._estado == "ouvindo"
    c.palavra_jarvis()  # eco/repetição logo em seguida: ignora
    assert tocadas == [saudacao]


def test_jarvis_mudo_ou_sem_frase_pronta_so_abre(dados_tmp):
    c, _, tocadas, janelas, iniciadas = _cerebro(dados_tmp, saude={"mudo": True})
    frase = frase_pronta("saudacao")
    frase.parent.mkdir(parents=True, exist_ok=True)
    frase.write_bytes(b"RIFF")
    c.palavra_jarvis()
    assert tocadas == [] and janelas == [1] and iniciadas == [1]
    frase.unlink()
    c2, _, tocadas2, _, _ = _cerebro(dados_tmp, saude={})
    c2.palavra_jarvis()
    assert tocadas2 == []


def test_jarvis_ignorado_quando_ja_ouve_ou_quando_a_propria_fala_disse_jarvis(dados_tmp):
    c, _, tocadas, janelas, iniciadas = _cerebro(dados_tmp, saude={})
    c.escuta.ativa = True
    c.palavra_jarvis()
    c.escuta.ativa = False
    c._estado, c._fala_atual = "falando", "Sou o Jarvis, senhor."
    c.palavra_jarvis()
    assert janelas == [] and iniciadas == []


def test_com_a_janela_aberta_jarvis_vale_como_super_j(dados_tmp):
    saudacao = frase_pronta("saudacao")
    saudacao.parent.mkdir(parents=True, exist_ok=True)
    saudacao.write_bytes(b"RIFF")
    c, chamadas, tocadas, janelas, iniciadas = _cerebro(dados_tmp, saude={"mudo": False})
    c.janela_aberta = True
    c._estado, c._fala_atual = "falando", "Os testes passaram, senhor."
    c.palavra_jarvis()  # interrompe a fala e já ouve, sem saudação
    assert chamadas[0] == "/parar"
    assert tocadas == [] and janelas == [] and iniciadas == [1]
    assert c._estado == "ouvindo"


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
