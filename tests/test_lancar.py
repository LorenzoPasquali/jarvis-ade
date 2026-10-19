import pytest

from conftest import ag
from jarvis import lancar

REPOS = [{"displayName": "dailytracker", "path": "/git/dailytracker"},
         {"displayName": "app-analise-saude", "path": "/git/app-analise-saude"}]


def test_planejar_reaproveita_sessao_parada():
    plano = lancar.planejar("dailytracker", "rodar testes", [ag("D", "done", projeto="dailytracker")], REPOS)
    assert plano["acao"] == "enviar" and plano["pane_key"] == "D" and plano["tarefa"] == "rodar testes"


def test_planejar_pergunta_se_trabalhando():
    plano = lancar.planejar("dailytracker", "x", [ag("D", "working", projeto="dailytracker")], REPOS)
    assert plano["acao"] == "perguntar" and "dailytracker" in plano["motivo"]


def test_planejar_abre_sem_sessao():
    plano = lancar.planejar("dailytracker", "x", [], REPOS)
    assert plano == {"acao": "abrir", "caminho": "/git/dailytracker", "tarefa": "x"}


def test_planejar_projeto_inexistente():
    with pytest.raises(ValueError):
        lancar.planejar("nao-existe", "x", [], REPOS)


def test_planejar_sem_diferenciar_maiusculas():
    assert lancar.planejar("DailyTracker", "x", [], REPOS)["caminho"] == "/git/dailytracker"


def test_lancamento_usa_orca_agent_launch(dados_tmp):
    chamadas = []
    lancar.executar_lancamento({"caminho": "/git/dailytracker", "tarefa": "rodar testes", "origem": "texto"},
                               executar=lambda a, **k: chamadas.append(a) or {})
    assert chamadas[0] == ["agent", "launch", "--agent", "claude", "--worktree", "path:/git/dailytracker",
                           "--prompt", "rodar testes"]
    assert '"tipo": "lancar"' in (dados_tmp / "acoes.jsonl").read_text()


def test_planejar_ambiguo_com_duas_sessoes_paradas():
    agentes = [ag("D1", "done", projeto="dailytracker", worktree="principal"),
               ag("D2", "waiting", projeto="dailytracker", worktree="feature-x")]
    with pytest.raises(ValueError) as e:
        lancar.planejar("dailytracker", "x", agentes, REPOS)
    assert "principal" in str(e.value) and "feature-x" in str(e.value)


def test_plano_de_envio_mostra_o_worktree():
    plano = lancar.planejar("dailytracker", "x", [ag("D", "done", projeto="dailytracker", worktree="feature-x")], REPOS)
    assert plano["worktree"] == "feature-x"
