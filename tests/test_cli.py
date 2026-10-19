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
