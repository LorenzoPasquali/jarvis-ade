import time

import pytest

from conftest import ag
from jarvis import cli, orca, pendencias, sessao
from jarvis.orca import Terminal


def test_criar_e_confirmar_regra(dados_tmp, regras_tmp):
    p = pendencias.criar("regra", "Nova regra", {"texto": "app-analise-saude: pode aprovar testes"})
    assert pendencias.listar()[0]["id"] == p["id"]
    feita = pendencias.confirmar(p["id"])
    texto = regras_tmp.read_text()
    assert "- app-analise-saude: pode aprovar testes" in texto and "(nenhuma)" not in texto
    assert feita["estado"] == "executada" and pendencias.listar() == []


def test_recusar_nao_executa(dados_tmp, regras_tmp):
    p = pendencias.criar("regra", "x", {"texto": "y"})
    assert pendencias.recusar(p["id"])["estado"] == "recusada"
    assert "- y" not in regras_tmp.read_text()


def test_pendencia_expira(dados_tmp, regras_tmp, monkeypatch):
    p = pendencias.criar("regra", "x", {"texto": "y"})
    agora = time.time()
    monkeypatch.setattr(pendencias.time, "time", lambda: agora + 601)
    assert pendencias.listar() == []
    with pytest.raises(ValueError):
        pendencias.confirmar(p["id"])
    assert "- y" not in regras_tmp.read_text()


def test_confirmar_duas_vezes_falha(dados_tmp, regras_tmp):
    p = pendencias.criar("regra", "x", {"texto": "y"})
    pendencias.confirmar(p["id"])
    with pytest.raises(ValueError):
        pendencias.confirmar(p["id"])


def test_ids_crescem(dados_tmp):
    a = pendencias.criar("regra", "a", {"texto": "a"})
    b = pendencias.criar("regra", "b", {"texto": "b"})
    assert b["id"] == a["id"] + 1


def test_regra_remover(dados_tmp, regras_tmp, capsys):
    pendencias.confirmar(pendencias.criar("regra", "a", {"texto": "primeira"})["id"])
    pendencias.confirmar(pendencias.criar("regra", "b", {"texto": "segunda"})["id"])
    assert cli.main(["regra", "remover", "1"]) == 0
    texto = regras_tmp.read_text()
    assert "- primeira" not in texto and "- segunda" in texto


def test_regra_adicionar_pelo_cli_vira_pendencia(dados_tmp, regras_tmp, capsys):
    assert cli.main(["regra", "adicionar", "todos: pode rodar testes"]) == 0
    assert "Aguardando confirmação" in capsys.readouterr().out
    assert "- todos: pode rodar testes" not in regras_tmp.read_text()
    assert pendencias.listar()[0]["tipo"] == "regra"


def test_enviar_por_voz_vira_pendencia(dados_tmp, capsys, monkeypatch):
    monkeypatch.setattr(orca, "agentes", lambda: [ag("S", "waiting", projeto="app-analise-saude")])
    monkeypatch.setattr(orca, "terminais", lambda: {"S": Terminal("term_s", "S", "/git/app-analise-saude", True)})
    monkeypatch.setattr(orca, "executar", lambda *a, **k: pytest.fail("não deveria enviar sem confirmação"))
    assert cli.main(["enviar", "--projeto", "app-analise-saude", "--texto", "segue", "--origem", "voz"]) == 0
    assert "Aguardando confirmação" in capsys.readouterr().out
    pendente = pendencias.listar()[0]
    assert pendente["tipo"] == "enviar" and pendente["dados"]["terminal"] == "term_s"
    assert "app-analise-saude" in pendente["descricao"] and "segue" in pendente["descricao"]


def test_cli_confirmar_e_listar(dados_tmp, regras_tmp, capsys):
    p = pendencias.criar("regra", "Nova regra: x", {"texto": "x"})
    cli.main(["pendencias"])
    assert f"{p['id']}" in capsys.readouterr().out
    assert cli.main(["confirmar", str(p["id"])]) == 0
    assert "- x" in regras_tmp.read_text()
    assert cli.main(["confirmar", str(p["id"])]) == 1


def test_tecla_por_voz_vira_pendencia_e_confirma(dados_tmp, capsys, monkeypatch):
    from jarvis import enviar
    monkeypatch.setattr(orca, "agentes", lambda: [ag("S", "permission", projeto="app-analise-saude")])
    monkeypatch.setattr(orca, "terminais", lambda: {"S": Terminal("term_s", "S", "/git/app-analise-saude", True)})
    assert cli.main(["enviar", "--projeto", "app-analise-saude", "--tecla", "1", "--origem", "voz"]) == 0
    p = pendencias.listar()[0]
    assert p["dados"]["tecla"] == "1" and "opção" in p["descricao"]
    chamadas = []
    monkeypatch.setattr(enviar, "_estado_no_orca", lambda pane: "permission")
    monkeypatch.setattr(orca, "executar", lambda args, **k: chamadas.append(args) or {})
    feita = pendencias.confirmar(p["id"])
    assert feita["estado"] == "executada" and chamadas[0][-1] == "1" and "--enter" not in chamadas[0]
