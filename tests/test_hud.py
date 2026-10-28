import json
import os
import signal
import subprocess
import sys

import pytest
from conftest import RAIZ
from jarvis import hud_cli


def test_index_tem_regioes():
    html = (RAIZ / "hud/index.html").read_text()
    for regiao in ["nucleo", "estado", "sessoes", "conversa", "cartoes", "entrada", "sistema", "veu"]:
        assert f'id="{regiao}"' in html
    assert 'lang="pt-BR"' in html


def test_fontes_locais_sem_cdn():
    css = (RAIZ / "hud/estilo.css").read_text()
    assert "@font-face" in css and "fonts.googleapis" not in css and "http" not in css.split("@font-face")[1][:400]
    assert "prefers-reduced-motion" in css
    assert (RAIZ / "hud/fontes/michroma.woff2").exists() and (RAIZ / "hud/fontes/saira.woff2").exists()


def test_app_trata_todos_os_eventos():
    js = (RAIZ / "hud/app.js").read_text()
    for tipo in ["estado", "nivel", "usuario", "delta", "resposta_fim", "sessoes", "cartao", "cartao_fim",
                 "sistema", "historico"]:
        assert f'"{tipo}"' in js or f"'{tipo}'" in js


def test_hud_alterna_janela_viva(dados_tmp, monkeypatch):
    sinais = []
    monkeypatch.setattr(hud_cli, "_janela_viva", lambda pid: True)
    monkeypatch.setattr(hud_cli.os, "kill", lambda pid, sig: sinais.append(sig))
    monkeypatch.setattr(hud_cli, "_avisar_cerebro", lambda: None)
    (dados_tmp / "hud.pid").write_text("4242")
    assert hud_cli.hud(demo=False) == 0 and sinais == [signal.SIGUSR1]


def test_hud_sem_janela_inicia_uma(dados_tmp, monkeypatch):
    iniciados = []
    monkeypatch.setattr(hud_cli, "_janela_viva", lambda pid: False)
    monkeypatch.setattr(hud_cli, "_iniciar_janela", lambda demo: iniciados.append(demo))
    monkeypatch.setattr(hud_cli, "_avisar_cerebro", lambda: None)
    assert hud_cli.hud(demo=True) == 0 and iniciados == [True]


def test_janela_e_transparente_e_por_cima():
    py = (RAIZ / "hud/janela.py").read_text()
    for trecho in ["get_rgba_visual", "set_app_paintable(True)", "set_background_color", "set_keep_above(True)",
                   "set_skip_taskbar_hint(True)", "fullscreen()", "SIGUSR1", "hud.pid"]:
        assert trecho in py, trecho


def test_app_cuida_de_cartao_vencido_e_resposta_em_andamento():
    js = (RAIZ / "hud/app.js").read_text()
    assert "status === 409" in js or "status == 409" in js
    assert 'replaceChildren()' in js.split('case "historico"')[1].split("break")[0]
    assert "escrevendo" in js.split('case "usuario"')[1].split("break")[0]


def test_janela_expandida_tem_botao_de_voz_e_reduzir():
    html = (RAIZ / "hud/index.html").read_text()
    js = (RAIZ / "hud/app.js").read_text()
    assert 'id="mudo"' in html and 'id="reduzir"' in html
    assert '"/api/mudo"' in js and 'postMessage("reduzir")' in js
    assert "mudo" in js.split("function sistema")[1].split("\n  }\n")[0]


def test_compacta_deixa_digitar_sem_os_botoes_de_voz_e_microfone():
    html = (RAIZ / "hud/aviso.html").read_text()
    assert 'id="digitar"' in html and '"/api/mensagem"' in html
    for fora in ['id="mudo"', 'id="microfone"', '"/api/mudo"', '"/api/microfone"']:
        assert fora not in html, fora


def test_janela_reduz_para_a_compacta_e_so_ela_pega_foco():
    py = (RAIZ / "hud/janela.py").read_text()
    assert '"reduzir"' in py and "self.mostrar_compacta()" in py.split('"reduzir"')[1]
    assert "set_accept_focus(True)" in py and "set_accept_focus(False)" in py
    assert "set_focus_on_map(False)" in py


def test_compacta_mantem_o_anel_sem_o_texto_jarvis_pronto():
    html = (RAIZ / "hud/aviso.html").read_text()
    estilo = html.split("<style>")[1].split("</style>")[0]
    assert "body.compacto .titulo" in estilo  # sem "Jarvis / Pronto" à vista
    assert "body.compacto .anel" not in estilo  # o anel continua o mesmo
    assert ".anel\").title" in html  # o nome do estado ainda aparece ao passar o mouse


def test_janela_expandida_tem_botao_do_microfone():
    assert 'id="microfone"' in (RAIZ / "hud/index.html").read_text()
    assert '"/api/microfone"' in (RAIZ / "hud/app.js").read_text()


# Abre a página num WebKit fora da tela e pergunta qual elemento está no centro de cada botão do topo.
# (`.click()` em JS não serve: chama o botão mesmo que outro elemento esteja por cima dele.)
QUEM_RECEBE_O_CLIQUE = """
import sys, gi
gi.require_version("Gtk", "3.0"); gi.require_version("WebKit2", "4.1")
from gi.repository import GLib, Gtk, WebKit2
janela = Gtk.OffscreenWindow(); janela.set_default_size(1600, 900)
web = WebKit2.WebView(); janela.add(web); janela.show_all()
JS = "JSON.stringify(['mudo','microfone','reduzir'].map(id => {" \\
     " const r = document.getElementById(id).getBoundingClientRect();" \\
     " const e = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2); return e && e.id; }))"
def pronto(w, res): print(w.evaluate_javascript_finish(res).to_string()); Gtk.main_quit()
web.connect("load-changed", lambda w, ev: ev == WebKit2.LoadEvent.FINISHED and
            GLib.timeout_add(300, lambda: w.evaluate_javascript(JS, -1, None, None, None, pronto) and False))
web.load_uri(sys.argv[1])
GLib.timeout_add(15000, Gtk.main_quit)
Gtk.main()
"""


def test_botoes_do_topo_da_janela_expandida_recebem_o_clique():
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        pytest.skip("sem tela para o WebKit")
    saida = subprocess.run([sys.executable, "-c", QUEM_RECEBE_O_CLIQUE, (RAIZ / "hud/index.html").as_uri()],
                           capture_output=True, text=True, timeout=30)
    if "No module named 'gi'" in saida.stderr or "Namespace WebKit2 not available" in saida.stderr:
        pytest.skip("sem WebKit2 4.1")
    assert json.loads(saida.stdout.strip().splitlines()[-1]) == ["mudo", "microfone", "reduzir"]
