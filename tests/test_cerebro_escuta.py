import struct
import subprocess

import pytest

from jarvis.cerebro.escuta import DetectorSilencio, rms, tela_bloqueada


def test_rms():
    assert rms(b"\x00\x00" * 160) == 0.0
    assert rms(struct.pack("<160h", *([16384] * 160))) == pytest.approx(0.5, abs=0.01)
    assert rms(b"") == 0.0


def test_detector_fim_depois_de_fala_e_silencio():
    d = DetectorSilencio()
    for t in (0.0, 0.1, 0.2, 0.5):
        assert d.alimentar(0.2, t) is None
    assert d.alimentar(0.0, 1.0) is None and d.alimentar(0.0, 2.1) == "fim"


def test_detector_fala_volta_reinicia_silencio():
    d = DetectorSilencio()
    for t in (0.0, 0.1, 0.2):
        d.alimentar(0.2, t)
    d.alimentar(0.0, 0.5)
    assert d.alimentar(0.2, 1.2) is None
    assert d.alimentar(0.0, 1.5) is None and d.alimentar(0.0, 2.0) is None and d.alimentar(0.0, 2.6) == "fim"


def test_detector_vazio_sem_fala():
    d = DetectorSilencio()
    assert d.alimentar(0.0, 3.0) is None and d.alimentar(0.0, 6.1) == "vazio"


def test_detector_maximo():
    d = DetectorSilencio()
    d.alimentar(0.02, 0.0)
    for t in (0.1, 0.2, 0.3):
        d.alimentar(0.3, t)
    assert d.alimentar(0.3, 30.1) == "fim"


def test_tela_bloqueada():
    def r(*a, **k):
        return subprocess.CompletedProcess(a[0], 0, stdout="(true,)\n", stderr="")

    def r2(*a, **k):
        return subprocess.CompletedProcess(a[0], 0, stdout="(false,)\n", stderr="")

    def falha(*a, **k):
        raise FileNotFoundError()

    assert tela_bloqueada(runner=r) is True
    assert tela_bloqueada(runner=r2) is False
    assert tela_bloqueada(runner=falha) is False


def test_ruido_do_microfone_nao_conta_como_fala():
    d = DetectorSilencio()
    ruido = [0.019, 0.025, 0.036, 0.042, 0.021, 0.03, 0.019, 0.028]
    resultado = None
    for i in range(70):
        resultado = d.alimentar(ruido[i % len(ruido)], i * 0.1)
        if resultado:
            break
    assert resultado == "vazio"


def test_fala_logo_no_inicio_sobre_ruido():
    d = DetectorSilencio()
    niveis = [0.15, 0.2, 0.18, 0.12, 0.16] + [0.022, 0.03, 0.019, 0.025] * 5
    resultados = [d.alimentar(n, i * 0.1) for i, n in enumerate(niveis)]
    assert "fim" in resultados and "vazio" not in resultados
    assert resultados.index("fim") * 0.1 == pytest.approx(1.4, abs=0.15)


def test_estalo_isolado_nao_e_fala():
    d = DetectorSilencio()
    niveis = [0.02, 0.022, 0.2, 0.021] + [0.02] * 60
    resultados = [d.alimentar(n, i * 0.1) for i, n in enumerate(niveis)]
    assert "fim" not in resultados and "vazio" in resultados


def test_escuta_sem_arquivo_libera_a_voz_e_termina(dados_tmp):
    import threading

    from jarvis.cerebro.escuta import Escuta

    chamadas, fim = [], threading.Event()
    resultado = {}
    e = Escuta(lambda n: None, lambda t: (resultado.setdefault("texto", t), fim.set()),
               chamar=lambda rota, corpo=None, **k: chamadas.append((rota, corpo)) or {},
               comando=["sleep", "10"])  # gravador que nunca cria o arquivo
    e.iniciar()
    e.encerrar()
    assert fim.wait(3)
    assert resultado["texto"] is None and not e.ativa
    assert ("/ouvindo", {"ligado": False}) in chamadas
