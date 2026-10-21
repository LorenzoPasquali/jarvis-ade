import json
import subprocess

from conftest import RAIZ
from jarvis import lancador


def test_hook_fala_aposentado_nao_fala(dados_tmp):
    r = subprocess.run([str(RAIZ / "bin/jarvis"), "hook-fala"], input=json.dumps({"last_assistant_message": "🔊 oi"}),
                       capture_output=True, text=True, timeout=10, env={"JARVIS_DADOS": str(dados_tmp), "PATH": "/usr/bin"})
    assert r.returncode == 0


def test_eventos_seguir_avisa_que_a_aba_foi_aposentada(dados_tmp):
    proc = subprocess.Popen([str(RAIZ / "bin/jarvis"), "eventos", "--seguir"], stdout=subprocess.PIPE, text=True,
                            env={"JARVIS_DADOS": str(dados_tmp), "PATH": "/usr/bin"})
    linha = proc.stdout.readline()
    proc.kill()
    assert "aposentad" in linha and "app" in linha


def test_instalar_para_o_gravador_antigo(dados_tmp, monkeypatch):
    import os
    import signal
    sinais = []
    (dados_tmp / "ptt.json").write_text(json.dumps({"pid": 4242, "inicio": 0}))
    monkeypatch.setattr(lancador, "_e_gravador", lambda pid: pid == 4242)
    monkeypatch.setattr(lancador.os, "kill", lambda pid, sig: sinais.append((pid, sig)))
    lancador.parar_gravador_antigo()
    assert sinais == [(4242, signal.SIGINT)] and not (dados_tmp / "ptt.json").exists()
