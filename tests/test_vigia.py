from conftest import ag
from jarvis import sessao
from jarvis.orca import OrcaErro
from jarvis.vigia import diferenca, passo


def test_transicoes_geram_eventos():
    antes = {"A": ag("A", "working"), "B": ag("B", "working"), "C": ag("C", "working")}
    depois = {"A": ag("A", "done"), "B": ag("B", "permission"), "D": ag("D", "working")}
    tipos = sorted(e["tipo"] for e in diferenca(antes, depois, "2026-10-19T12:00:00"))
    assert tipos == ["permissao", "sessao_aberta", "sessao_fechada", "terminou"]


def test_aguardando_e_travou():
    antes = {"A": ag("A", "working"), "B": ag("B", "working")}
    depois = {"A": ag("A", "waiting"), "B": ag("B", "blocked")}
    assert sorted(e["tipo"] for e in diferenca(antes, depois, "t")) == ["aguardando", "travou"]


def test_working_e_idle_nao_geram_evento():
    assert diferenca({"A": ag("A", "done")}, {"A": ag("A", "working")}, "t") == []
    assert diferenca({"A": ag("A", "working")}, {"A": ag("A", "idle")}, "t") == []


def test_evento_tem_campos_e_resumo_cortado():
    e = diferenca({"A": ag("A", "working")}, {"A": ag("A", "done", mensagem="x" * 500)}, "t")[0]
    assert set(e) == {"id", "em", "tipo", "projeto", "worktree", "caminho", "pane_key", "agente", "estado", "resumo"}
    assert len(e["resumo"]) == 300 and e["em"] == "t"


def test_primeira_execucao_so_grava_linha_base(dados_tmp):
    assert passo(obter=lambda: [ag("A", "done")]) == []
    assert passo(obter=lambda: [ag("A", "done")]) == []


T0 = "2026-10-19T12:00:00-03:00"


def t(segundos: int) -> str:
    from datetime import datetime, timedelta
    return (datetime.fromisoformat(T0) + timedelta(seconds=segundos)).isoformat()


def test_reinicio_nao_reanuncia(dados_tmp):
    passo(obter=lambda: [ag("A", "working")], agora_iso=t(0))
    passo(obter=lambda: [ag("A", "done")], agora_iso=t(5))
    assert len(passo(obter=lambda: [ag("A", "done")], agora_iso=t(25))) == 1
    assert passo(obter=lambda: [ag("A", "done")], agora_iso=t(30)) == []


def test_terminou_espera_estabilizar(dados_tmp):
    passo(obter=lambda: [ag("A", "working")], agora_iso=t(0))
    assert passo(obter=lambda: [ag("A", "done")], agora_iso=t(5)) == []
    assert passo(obter=lambda: [ag("A", "done")], agora_iso=t(10)) == []
    eventos_ = passo(obter=lambda: [ag("A", "done", mensagem="pronto")], agora_iso=t(21))
    assert [e["tipo"] for e in eventos_] == ["terminou"] and eventos_[0]["resumo"] == "pronto"


def test_terminou_que_volta_a_trabalhar_nao_e_anunciado(dados_tmp):
    passo(obter=lambda: [ag("A", "working")], agora_iso=t(0))
    passo(obter=lambda: [ag("A", "done")], agora_iso=t(5))
    passo(obter=lambda: [ag("A", "working")], agora_iso=t(10))
    assert passo(obter=lambda: [ag("A", "working")], agora_iso=t(40)) == []


def test_permissao_e_imediata(dados_tmp):
    passo(obter=lambda: [ag("A", "working")], agora_iso=t(0))
    assert [e["tipo"] for e in passo(obter=lambda: [ag("A", "permission")], agora_iso=t(5))] == ["permissao"]


def test_exclui_sessao_jarvis(dados_tmp):
    sessao.registrar("J", "term_j")
    passo(obter=lambda: [ag("J", "working")])
    assert passo(obter=lambda: [ag("J", "done")]) == []


def test_orca_cai_e_volta_uma_vez(dados_tmp):
    passo(obter=lambda: [ag("A", "working")])

    def cai():
        raise OrcaErro("runtime_unavailable", "x")

    assert [e["tipo"] for e in passo(obter=cai)] == ["orca_indisponivel"]
    assert passo(obter=cai) == []
    assert [e["tipo"] for e in passo(obter=lambda: [ag("A", "working")])] == ["orca_disponivel"]


def test_eventos_sao_gravados_no_log(dados_tmp):
    from jarvis import eventos

    passo(obter=lambda: [ag("A", "working")], agora_iso=t(0))
    passo(obter=lambda: [ag("A", "blocked")], agora_iso=t(5))
    lidos, _ = eventos.ler_desde(0)
    assert [e["tipo"] for e in lidos] == ["travou"]
