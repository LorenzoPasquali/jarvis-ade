import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from jarvis import eventos, pendencias
from jarvis.cerebro import main as cerebro_main
from jarvis.cerebro.eventos import FilaEventos
from jarvis.cerebro.main import Cerebro
from jarvis.cerebro.servidor import criar


def ev(tipo, projeto="app-analise-saude"):
    return {"id": tipo, "em": "2026-10-19T12:00:00-03:00", "tipo": tipo, "projeto": projeto, "worktree": projeto,
            "caminho": f"/git/{projeto}", "pane_key": "S", "agente": "claude", "estado": "", "resumo": "feito"}


class ClaudeFalso:
    def __init__(self):
        self.ocupado = False
        self.enviados = []

    def enviar(self, texto):
        self.enviados.append(texto)
        self.ocupado = True


@pytest.fixture
def cerebro_falso(dados_tmp):
    claude = ClaudeFalso()
    c = Cerebro(claude=claude, falar=lambda t: True, bloqueada=lambda: False, chamar_voz=lambda *a, **k: {})
    return c, claude


def test_fila_filtra_tipos(dados_tmp):
    for tipo in ["sessao_aberta", "terminou", "orca_disponivel", "permissao"]:
        eventos.anexar(ev(tipo))
    f = FilaEventos(dados_tmp / "cerebro-cursor")
    f.coletar()
    linhas = f.retirar()
    assert len(linhas) == 2 and "terminou" in linhas[0] and "pedindo permissão" in linhas[1]
    assert f.vazia


def test_fila_nao_repete_depois_de_reiniciar(dados_tmp):
    eventos.anexar(ev("terminou"))
    f = FilaEventos(dados_tmp / "cerebro-cursor")
    f.coletar()
    f.retirar()
    outra = FilaEventos(dados_tmp / "cerebro-cursor")
    outra.coletar()
    assert outra.vazia


def test_evento_espera_turno_do_usuario(cerebro_falso):
    c, claude = cerebro_falso
    c.mensagem_usuario("como estão os projetos?", falada=False)
    eventos.anexar(ev("terminou"))
    c.laco_uma_vez()
    assert claude.enviados == ["como estão os projetos?"]
    claude.ocupado = False
    c.laco_uma_vez()
    assert claude.enviados[1].startswith("[eventos]\n")


def test_mensagem_durante_turno_vai_para_fila(cerebro_falso):
    c, claude = cerebro_falso
    c.mensagem_usuario("primeira", falada=False)
    c.mensagem_usuario("segunda", falada=True)
    assert claude.enviados == ["primeira"]
    claude.ocupado = False
    c.laco_uma_vez()
    assert claude.enviados == ["primeira", "[voz] segunda"]


def test_tela_bloqueada_segura_e_resume(cerebro_falso):
    c, claude = cerebro_falso
    c.bloqueada = lambda: True
    eventos.anexar(ev("terminou"))
    c.laco_uma_vez()
    assert claude.enviados == []
    c.bloqueada = lambda: False
    c.laco_uma_vez()
    assert claude.enviados[0].startswith("[sistema] O senhor voltou.")


def test_resposta_vai_para_historico_e_voz(dados_tmp):
    falas, publicados = [], []
    c = Cerebro(claude=ClaudeFalso(), falar=lambda t: falas.append(t) or True, bloqueada=lambda: False,
                chamar_voz=lambda *a, **k: {})
    c.publicar = publicados.append
    for pedaco in ["Olá, senhor.\n", "🔊 Tudo ", "certo.\n"]:
        c.ao_evento_claude({"type": "stream_event", "event": {"type": "content_block_delta",
                                                              "delta": {"type": "text_delta", "text": pedaco}}})
    c.ao_evento_claude({"type": "result", "result": "Olá, senhor.\n🔊 Tudo certo.\n"})
    assert falas == ["Tudo certo."]
    assert {"tipo": "delta", "texto": "Olá, senhor.\n"} in publicados
    assert any(p["tipo"] == "resposta_fim" for p in publicados)
    historico = [json.loads(linha) for linha in (dados_tmp / "conversa.jsonl").read_text().splitlines()]
    assert historico[-1]["papel"] == "jarvis" and "Tudo certo" in historico[-1]["texto"]


def test_claude_reiniciando_publica_estado(cerebro_falso):
    c, _ = cerebro_falso
    publicados = []
    c.publicar = publicados.append
    c.ao_evento_claude({"type": "jarvis_reiniciando"})
    assert {"tipo": "estado", "valor": "desconectado"} in publicados


def test_permissao_sem_resposta_nega(cerebro_falso, monkeypatch):
    c, _ = cerebro_falso
    monkeypatch.setattr(cerebro_main, "ESPERA_PERMISSAO_S", 0.2)
    assert c.pedir_permissao("Bash", {"command": "rm x"}) is False


def test_permissao_aprovada_pelo_cartao(cerebro_falso):
    c, _ = cerebro_falso
    publicados = []
    c.publicar = publicados.append
    resultado = {}
    t = threading.Thread(target=lambda: resultado.setdefault("ok", c.pedir_permissao("WebFetch", {"url": "x"})))
    t.start()
    for _ in range(50):
        cartoes = [p for p in publicados if p["tipo"] == "cartao"]
        if cartoes:
            break
        time.sleep(0.02)
    c.decidir_cartao(cartoes[0]["id"], "aprovar")
    t.join(2)
    assert resultado["ok"] is True


def test_pendencia_aberta_vira_cartao(cerebro_falso, regras_tmp):
    c, _ = cerebro_falso
    publicados = []
    c.publicar = publicados.append
    p = pendencias.criar("regra", "Nova regra: «x»", {"texto": "x"})
    c.laco_uma_vez()
    assert {"tipo": "cartao", "id": p["id"], "tipo_pendencia": "regra", "descricao": "Nova regra: «x»"} in publicados


# ---------- servidor ----------

@pytest.fixture
def servidor_cerebro(cerebro_falso):
    c, _ = cerebro_falso
    srv = criar(c, porta=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", c
    srv.shutdown()


def post(url, corpo, origin=None, tipo="application/json"):
    cabecalhos = {"Content-Type": tipo}
    if origin:
        cabecalhos["Origin"] = origin
    req = urllib.request.Request(url, data=json.dumps(corpo).encode(), headers=cabecalhos)
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def ler_sse(url, ate, depois=None, limite=40):
    resposta = urllib.request.urlopen(url, timeout=5)
    if depois:
        threading.Timer(0.2, depois).start()
    recebidos = []
    while len(recebidos) < limite:
        linha = resposta.readline().decode()
        if linha.startswith("data: "):
            recebidos.append(json.loads(linha[6:]))
            if ate(recebidos[-1]):
                break
    resposta.close()
    return recebidos


def test_sse_recebe_historico_e_delta(servidor_cerebro):
    base, c = servidor_cerebro
    linhas = ler_sse(base + "/api/eventos", ate=lambda e: e["tipo"] == "delta",
                     depois=lambda: c.publicar({"tipo": "delta", "texto": "oi"}))
    assert linhas[0]["tipo"] == "historico" and {"tipo": "delta", "texto": "oi"} in linhas


def test_serve_a_janela(servidor_cerebro):
    base, _ = servidor_cerebro
    html = urllib.request.urlopen(base + "/", timeout=3).read().decode()
    assert 'id="nucleo"' in html
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(base + "/../jarvis/config.py", timeout=3)


def test_post_de_outra_origem_recusado(servidor_cerebro):
    base, _ = servidor_cerebro
    assert post(base + "/api/mensagem", {"texto": "x"}, origin="https://exemplo.com") == 403
    assert post(base + "/api/mensagem", {"texto": "x"}, tipo="text/plain") == 415


def test_post_da_propria_janela_aceito(servidor_cerebro):
    base, c = servidor_cerebro
    assert post(base + "/api/mensagem", {"texto": "oi"}, origin=base) == 202
    assert c.claude.enviados == ["oi"]


def test_cartao_aprovado_confirma_pendencia(servidor_cerebro, regras_tmp):
    base, _ = servidor_cerebro
    p = pendencias.criar("regra", "x", {"texto": "y"})
    assert post(base + "/api/cartao", {"id": p["id"], "decisao": "aprovar"}) == 200
    assert "- y" in regras_tmp.read_text()


def test_origem_null_recusada(servidor_cerebro):
    base, _ = servidor_cerebro
    assert post(base + "/api/mensagem", {"texto": "x"}, origin="null") == 403
