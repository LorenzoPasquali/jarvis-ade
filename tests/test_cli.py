import subprocess

import pytest

from conftest import RAIZ


def test_help_lista_subcomandos(capsys):
    from jarvis.cli import main

    with pytest.raises(SystemExit):
        main(["--help"])
    saida = capsys.readouterr().out
    for sub in ["iniciar", "status", "eventos", "historico", "clima", "enviar",
                "vigia", "hook-fala", "ouvir", "calar", "mudo", "instalar"]:
        assert sub in saida


def test_bin_jarvis_executa():
    r = subprocess.run([str(RAIZ / "bin/jarvis"), "--help"], capture_output=True, text=True)
    assert r.returncode == 0


def test_mudo_passa_pelo_cerebro_para_o_botao_mudar_na_hora(monkeypatch, capsys):
    from jarvis import cli, hud_cli, voz_cliente

    pedidos = []
    monkeypatch.setattr(hud_cli, "chamar_cerebro", lambda rota, corpo=None: pedidos.append((rota, corpo)) or True)
    monkeypatch.setattr(voz_cliente, "mudo", lambda ligado: pytest.fail("o cérebro já repassou à voz"))
    assert cli.main(["mudo", "on"]) == 0
    assert pedidos == [("/api/mudo", {"ligado": True})]


def test_mudo_sem_cerebro_vai_direto_a_voz(monkeypatch):
    from jarvis import cli, hud_cli, voz_cliente

    direto = []
    monkeypatch.setattr(hud_cli, "chamar_cerebro", lambda rota, corpo=None: False)
    monkeypatch.setattr(voz_cliente, "mudo", lambda ligado: direto.append(ligado))
    assert cli.main(["mudo", "off"]) == 0
    assert direto == [False]
