import subprocess

import pytest

from conftest import carregar
from jarvis.orca import OrcaErro, executar, listar_agentes, mapa_terminais


def runner_falso(stdout: str, code: int = 0):
    def runner(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], code, stdout=stdout, stderr="")
    return runner


def test_listar_agentes_ignora_subagentes():
    ags = listar_agentes(carregar("worktree_ps.json"))
    assert [a.pane_key for a in ags] == ["TAB-J:LEAF-J", "TAB-S:LEAF-S"]
    assert ags[1].projeto == "app-analise-saude" and ags[1].estado == "waiting"
    assert ags[0].ultima_mensagem == ""


def test_mapa_terminais_por_pane():
    m = mapa_terminais(carregar("terminal_list.json"))
    assert m["TAB-S:LEAF-S"].handle.startswith("term_") and m["TAB-S:LEAF-S"].gravavel
    assert not m["TAB-F:LEAF-F"].gravavel


def test_executar_devolve_result():
    r = executar(["repo", "list"], runner=runner_falso('{"ok":true,"result":{"repos":[]}}'))
    assert r == {"repos": []}


def test_runtime_indisponivel_vira_orca_erro():
    runner = runner_falso('{"ok":false,"error":{"code":"runtime_unavailable","message":"x"}}', code=1)
    with pytest.raises(OrcaErro) as e:
        executar(["worktree", "ps"], runner=runner)
    assert e.value.codigo == "runtime_unavailable"


def test_timeout_vira_orca_erro():
    def runner(*a, **k):
        raise subprocess.TimeoutExpired("orca", 10)
    with pytest.raises(OrcaErro) as e:
        executar(["worktree", "ps"], runner=runner)
    assert e.value.codigo == "timeout"


def test_binario_ausente():
    def runner(*a, **k):
        raise FileNotFoundError()
    with pytest.raises(OrcaErro) as e:
        executar(["repo", "list"], runner=runner)
    assert e.value.codigo == "cli_indisponivel"


def test_json_invalido():
    with pytest.raises(OrcaErro) as e:
        executar(["repo", "list"], runner=runner_falso("isto não é json"))
    assert e.value.codigo == "resposta_invalida"
