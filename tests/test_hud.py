import signal

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


def test_compacta_deixa_digitar_e_tem_botao_de_voz():
    html = (RAIZ / "hud/aviso.html").read_text()
    assert 'id="digitar"' in html and 'id="mudo"' in html
    assert '"/api/mensagem"' in html and '"/api/mudo"' in html
    assert 'case "sistema"' in html


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


def test_janelas_tem_botao_do_microfone():
    for pagina in ["index.html", "aviso.html"]:
        assert 'id="microfone"' in (RAIZ / f"hud/{pagina}").read_text(), pagina
    assert '"/api/microfone"' in (RAIZ / "hud/app.js").read_text()
    assert '"/api/microfone"' in (RAIZ / "hud/aviso.html").read_text()
