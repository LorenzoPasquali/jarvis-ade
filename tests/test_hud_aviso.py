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
