import json

import pytest

from conftest import ag
from jarvis.enviar import Destino, EnvioRecusado, enviar, resolver_destino
from jarvis.orca import OrcaErro, Terminal

AGENTES = [ag("P-JARVIS", "working", projeto="jarvis"), ag("P-SAUDE", "waiting", projeto="app-analise-saude")]
TERMINAIS = {"P-JARVIS": Terminal("term_j", "P-JARVIS", "/git/jarvis", True),
             "P-SAUDE": Terminal("term_saude", "P-SAUDE", "/git/app-analise-saude", True)}
SESSAO = {"pane_key": "P-JARVIS", "terminal": "term_j"}
DEST = Destino(terminal="term_saude", pane_key="P-SAUDE", projeto="app-analise-saude", caminho="/git/app-analise-saude")


def ler_acoes(dados):
    return [json.loads(linha) for linha in (dados / "acoes.jsonl").read_text().splitlines()]


def falso_ok(args, **kwargs):
    return {}


def esperando(pane):
    return "waiting"


def permissao(pane):
    return "permission"


def test_resolve_por_projeto_sem_diferenciar_maiusculas():
    d = resolver_destino("App-Analise-Saude", None, AGENTES, TERMINAIS, SESSAO)
    assert d.terminal == "term_saude" and d.projeto == "app-analise-saude"


def test_resolve_por_terminal():
    assert resolver_destino(None, "term_saude", AGENTES, TERMINAIS, SESSAO).pane_key == "P-SAUDE"


def test_recusa_sessao_jarvis_por_projeto():
    with pytest.raises(EnvioRecusado):
        resolver_destino("jarvis", None, AGENTES, TERMINAIS, SESSAO)


def test_recusa_sessao_jarvis_por_terminal():
    with pytest.raises(EnvioRecusado):
        resolver_destino(None, "term_j", AGENTES, TERMINAIS, SESSAO)


def test_recusa_ambiguo_lista_opcoes():
    agentes = [ag("S1", "waiting", projeto="saude"), ag("S2", "done", projeto="saude")]
    terms = {"S1": Terminal("term_s1", "S1", "/git/saude", True), "S2": Terminal("term_s2", "S2", "/git/saude", True)}
    with pytest.raises(EnvioRecusado) as e:
        resolver_destino("saude", None, agentes, terms, None)
    assert "term_s1" in str(e.value) and "term_s2" in str(e.value)


def test_recusa_nao_encontrado():
    with pytest.raises(EnvioRecusado):
        resolver_destino("inexistente", None, AGENTES, TERMINAIS, SESSAO)


def test_recusa_terminal_nao_gravavel():
    terms = {**TERMINAIS, "P-SAUDE": Terminal("term_saude", "P-SAUDE", "/git/app-analise-saude", False)}
    with pytest.raises(EnvioRecusado):
        resolver_destino("app-analise-saude", None, AGENTES, terms, SESSAO)


def test_voz_sem_confirmacao_recusa_e_registra(dados_tmp):
    with pytest.raises(EnvioRecusado):
        enviar(DEST, texto="segue", tecla=None, origem="voz", motivo="", confirmado=False, executar=falso_ok, estado_atual=esperando)
    assert ler_acoes(dados_tmp)[-1]["resultado"].startswith("recusado")


def test_regra_exige_motivo(dados_tmp):
    with pytest.raises(EnvioRecusado):
        enviar(DEST, texto="1", tecla=None, origem="regra", motivo="", confirmado=False, executar=falso_ok, estado_atual=esperando)


def test_exige_exatamente_texto_ou_tecla(dados_tmp):
    with pytest.raises(EnvioRecusado):
        enviar(DEST, texto="a", tecla="1", origem="texto", motivo="", confirmado=False, executar=falso_ok, estado_atual=esperando)
    with pytest.raises(EnvioRecusado):
        enviar(DEST, texto=None, tecla=None, origem="texto", motivo="", confirmado=False, executar=falso_ok, estado_atual=esperando)


def test_texto_envia_com_enter_e_registra(dados_tmp):
    chamadas = []
    enviar(DEST, texto="segue com o plano", tecla=None, origem="texto", motivo="ordem", confirmado=False,
           executar=lambda args, **k: chamadas.append(args) or {}, estado_atual=esperando)
    assert chamadas[0] == ["terminal", "send", "--terminal", "term_saude", "--text", "segue com o plano", "--enter"]
    acao = ler_acoes(dados_tmp)[-1]
    assert acao["resultado"] == "ok" and acao["projeto"] == "app-analise-saude" and acao["origem"] == "texto"


def test_voz_confirmada_envia(dados_tmp):
    enviar(DEST, texto="segue", tecla=None, origem="voz", motivo="", confirmado=True, executar=falso_ok, estado_atual=esperando)
    assert ler_acoes(dados_tmp)[-1]["confirmado"] is True


def test_tecla_sem_enter(dados_tmp):
    chamadas = []
    enviar(DEST, texto=None, tecla="1", origem="regra", motivo="regra: testes liberados", confirmado=False,
           executar=lambda args, **k: chamadas.append(args) or {}, estado_atual=permissao)
    assert "--enter" not in chamadas[0] and chamadas[0][-1] == "1"


def test_falha_do_orca_registra_erro(dados_tmp):
    def falha(args, **k):
        raise OrcaErro("runtime_unavailable", "x")
    with pytest.raises(OrcaErro):
        enviar(DEST, texto="oi", tecla=None, origem="texto", motivo="", confirmado=False, executar=falha,
               estado_atual=esperando)
    assert ler_acoes(dados_tmp)[-1]["resultado"] == "erro: runtime_unavailable"


def test_recusa_terminal_sem_agente():
    terms = {**TERMINAIS, "P-SHELL": Terminal("term_root_vps", "P-SHELL", "/opt", True)}
    with pytest.raises(EnvioRecusado) as e:
        resolver_destino(None, "term_root_vps", AGENTES, terms, SESSAO)
    assert "agente" in str(e.value)


@pytest.mark.parametrize("texto", ["!rm -rf /", "  !ls", "/clear", " /compact"])
def test_recusa_shell_e_comandos_de_barra(dados_tmp, texto):
    with pytest.raises(EnvioRecusado):
        enviar(DEST, texto=texto, tecla=None, origem="texto", motivo="x", confirmado=False,
               executar=lambda *a, **k: pytest.fail("não deveria enviar"), estado_atual=esperando)


@pytest.mark.parametrize("tecla", ["123", "1;", "\x1b", " ", "y\n"])
def test_recusa_tecla_fora_do_padrao(dados_tmp, tecla):
    with pytest.raises(EnvioRecusado):
        enviar(DEST, texto=None, tecla=tecla, origem="regra", motivo="regra", confirmado=False,
               executar=lambda *a, **k: pytest.fail("não deveria enviar"), estado_atual=permissao)


def test_texto_recusado_durante_pedido_de_permissao(dados_tmp):
    with pytest.raises(EnvioRecusado) as e:
        enviar(DEST, texto="não faça isso", tecla=None, origem="texto", motivo="x", confirmado=False,
               executar=lambda *a, **k: pytest.fail("Enter aprovaria a permissão"), estado_atual=permissao)
    assert "permissão" in str(e.value)
    assert ler_acoes(dados_tmp)[-1]["resultado"].startswith("recusado")


def test_tecla_exige_pergunta_aberta(dados_tmp):
    with pytest.raises(EnvioRecusado):
        enviar(DEST, texto=None, tecla="1", origem="regra", motivo="regra", confirmado=False,
               executar=lambda *a, **k: pytest.fail("não deveria enviar"), estado_atual=lambda p: "working")


def test_recusa_sessao_que_fechou(dados_tmp):
    with pytest.raises(EnvioRecusado):
        enviar(DEST, texto="oi", tecla=None, origem="texto", motivo="x", confirmado=False,
               executar=lambda *a, **k: pytest.fail("não deveria enviar"), estado_atual=lambda p: None)
