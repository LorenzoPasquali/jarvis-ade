import time

import pytest

from jarvis import cli, pendencias, turno


@pytest.fixture
def no_cerebro(dados_tmp, monkeypatch):
    monkeypatch.setenv("JARVIS_CEREBRO", "1")
    return dados_tmp


def test_fora_do_cerebro_nao_restringe(dados_tmp, monkeypatch):
    monkeypatch.delenv("JARVIS_CEREBRO", raising=False)
    turno.exigir("enviar", "texto")


@pytest.mark.parametrize("tipo,acao,origem,permitido", [
    ("texto", "enviar", "texto", True),
    ("eventos", "enviar", "texto", False),
    ("sistema", "enviar", "texto", False),
    ("voz", "enviar", "voz", True),
    ("eventos", "enviar", "voz", False),
    ("eventos", "enviar", "regra", True),
    ("texto", "enviar", "regra", False),
    ("texto", "lancar", "texto", True),
    ("eventos", "lancar", "texto", False),
    ("sistema", "lancar", "voz", False),
])
def test_origem_casada_com_o_turno(no_cerebro, tipo, acao, origem, permitido):
    turno.registrar(tipo)
    if permitido:
        turno.exigir(acao, origem)
    else:
        with pytest.raises(turno.ForaDoTurno):
            turno.exigir(acao, origem)


def test_sem_turno_ativo_recusa(no_cerebro):
    turno.registrar("texto")
    turno.encerrar()
    with pytest.raises(turno.ForaDoTurno):
        turno.exigir("enviar", "texto")


def test_confirmar_so_em_turno_de_voz_posterior(no_cerebro, regras_tmp):
    p = pendencias.criar("regra", "x", {"texto": "y"})
    turno.registrar("eventos")
    with pytest.raises(turno.ForaDoTurno):
        turno.exigir_confirmacao(p)
    time.sleep(0.01)
    turno.registrar("voz")
    turno.exigir_confirmacao(p)
    velho = {**p, "criada_ts": time.time() + 60}
    with pytest.raises(turno.ForaDoTurno):
        turno.exigir_confirmacao(velho)


def test_cli_confirmar_em_turno_de_eventos_recusa(no_cerebro, regras_tmp, capsys):
    p = pendencias.criar("regra", "x", {"texto": "y"})
    turno.registrar("eventos")
    assert cli.main(["confirmar", str(p["id"])]) == 1
    assert "- y" not in regras_tmp.read_text()


def test_cli_lancar_em_turno_de_eventos_recusa(no_cerebro, capsys, monkeypatch):
    from jarvis import orca
    monkeypatch.setattr(orca, "agentes", lambda: pytest.fail("nem deveria consultar o Orca"))
    turno.registrar("eventos")
    assert cli.main(["lancar", "--projeto", "x", "--tarefa", "y", "--origem", "texto"]) == 1
