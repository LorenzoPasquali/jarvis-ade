import importlib.util
import sys

import pytest

from conftest import RAIZ

pytest.importorskip("gi")


@pytest.fixture(scope="module")
def janela():
    spec = importlib.util.spec_from_file_location("janela_hud", RAIZ / "hud/janela.py")
    modulo = importlib.util.module_from_spec(spec)
    argv = sys.argv
    try:
        spec.loader.exec_module(modulo)
    except (ImportError, ValueError) as erro:  # sem GTK/WebKit na máquina
        pytest.skip(str(erro))
    finally:
        sys.argv = argv
    return modulo


class Display:
    def __init__(self, monitores, da_janela=None, do_ponteiro=None):
        self.monitores, self.da_janela, self.do_ponteiro = monitores, da_janela, do_ponteiro

    def get_monitor_at_window(self, _janela):
        return self.da_janela

    def get_default_seat(self):
        return self

    def get_pointer(self):
        return self

    def get_position(self):
        return None, 10, 10

    def get_monitor_at_point(self, _x, _y):
        return self.do_ponteiro

    def get_n_monitors(self):
        return len(self.monitores)

    def get_monitor(self, i):
        return self.monitores[i]


class Tela:
    def __init__(self, display, ativa):
        self.display, self.ativa = display, ativa

    def get_display(self):
        return self.display

    def get_active_window(self):
        return self.ativa


def test_abre_no_monitor_da_janela_com_foco(janela):
    hdmi, edp, dp = object(), object(), object()
    tela = Tela(Display([edp, hdmi, dp], da_janela=dp, do_ponteiro=hdmi), ativa=object())
    assert janela.monitor_do_foco(tela) == 2


def test_sem_janela_ativa_usa_o_monitor_do_ponteiro(janela):
    hdmi, edp = object(), object()
    assert janela.monitor_do_foco(Tela(Display([edp, hdmi], do_ponteiro=hdmi), ativa=None)) == 1


def test_monitor_desconhecido_cai_no_padrao(janela):
    assert janela.monitor_do_foco(Tela(Display([object()], do_ponteiro=object()), ativa=None)) is None


class Ativa:
    def __init__(self, xid):
        self.xid = xid

    def get_xid(self):
        return self.xid


def _xprop(monkeypatch, janela, saida):
    class R:
        stdout = saida
    monkeypatch.setattr(janela.subprocess, "run", lambda *a, **k: R())


def test_app_na_frente_abre_compacto(janela, monkeypatch):
    _xprop(monkeypatch, janela, "_NET_WM_WINDOW_TYPE(ATOM) = _NET_WM_WINDOW_TYPE_NORMAL\n")
    assert janela.app_em_foco(Tela(None, ativa=Ativa(0x3200003)), proprias={0x260000d})


def test_area_de_trabalho_minimizado_ou_o_proprio_jarvis_abrem_inteiro(janela, monkeypatch):
    _xprop(monkeypatch, janela, "_NET_WM_WINDOW_TYPE(ATOM) = _NET_WM_WINDOW_TYPE_DESKTOP\n")
    assert not janela.app_em_foco(Tela(None, ativa=Ativa(0x1)), proprias=set())
    _xprop(monkeypatch, janela, "_NET_WM_WINDOW_TYPE_NORMAL\n_NET_WM_STATE(ATOM) = _NET_WM_STATE_HIDDEN\n")
    assert not janela.app_em_foco(Tela(None, ativa=Ativa(0x2)), proprias=set())
    assert not janela.app_em_foco(Tela(None, ativa=None), proprias=set())
    assert not janela.app_em_foco(Tela(None, ativa=Ativa(0x260000d)), proprias={0x260000d})
