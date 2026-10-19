from conftest import RAIZ


def test_aviso_existe_e_nao_rouba_foco():
    html = (RAIZ / "hud/aviso.html").read_text()
    assert 'id="aviso"' in html and "EventSource" in html and "mostrar_aviso" in html and "esconder_aviso" in html
    py = (RAIZ / "hud/janela.py").read_text()
    assert "set_accept_focus(False)" in py and "set_focus_on_map(False)" in py and "aviso.html" in py


def test_app_reconecta_e_mostra_desconectado():
    js = (RAIZ / "hud/app.js").read_text()
    assert "EventSource" in js and "desconectado" in js and "Jarvis desconectado" in js
    assert '"/api/fechar"' in js and '"/api/mensagem"' in js and '"/api/cartao"' in js


def test_janela_recarrega_quando_o_cerebro_ainda_nao_subiu():
    py = (RAIZ / "hud/janela.py").read_text()
    assert '"load-failed"' in py and '"web-process-terminated"' in py


def test_cerebro_abre_a_porta_antes_de_checar_o_orca():
    import inspect

    from jarvis.cerebro import main as cerebro_main
    fonte = inspect.getsource(cerebro_main.main)
    assert fonte.index("criar(cerebro") < fonte.index("garantir_orca()")
