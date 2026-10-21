#!/usr/bin/env python3
"""Janela do Jarvis: tela inteira, fundo transparente, sempre por cima.

Começa escondida (exceto com --mostrar). `SIGUSR1` mostra a janela e chama `jarvis.abrir()` na página;
a página pede para esconder com `webkit.messageHandlers.jarvis.postMessage("fechar")`.
"""

import argparse
import os
import signal
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gdk, GLib, Gtk, WebKit2  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from jarvis.config import dados  # noqa: E402

URL_PADRAO = "http://127.0.0.1:8766/"
LARGURA_AVISO, ALTURA_AVISO = 460, 112


def _janela_transparente(janela: Gtk.Window) -> None:
    janela.set_decorated(False)
    janela.set_keep_above(True)
    janela.set_skip_taskbar_hint(True)
    janela.set_skip_pager_hint(True)
    visual = janela.get_screen().get_rgba_visual()
    if visual is not None:
        janela.set_visual(visual)
    janela.set_app_paintable(True)


def _webview(ao_mensagem) -> WebKit2.WebView:
    conteudo = WebKit2.UserContentManager()
    conteudo.register_script_message_handler("jarvis")
    conteudo.connect("script-message-received::jarvis", ao_mensagem)
    web = WebKit2.WebView.new_with_user_content_manager(conteudo)
    web.set_background_color(Gdk.RGBA(0, 0, 0, 0))
    # No login a janela pode subir antes do cérebro: em vez de ficar na página de erro, tenta de novo.
    web.connect("load-failed", lambda w, _evento, uri, _erro: _carregar_depois(w, uri))
    web.connect("web-process-terminated", lambda w, _motivo: _carregar_depois(w, w.get_uri()))
    return web


def monitor_do_foco(tela: Gdk.Screen) -> int | None:
    """Índice do monitor da janela com foco (ou, sem ela, do ponteiro): o Jarvis abre onde o senhor está."""
    display = tela.get_display()
    ativa = tela.get_active_window()  # _NET_ACTIVE_WINDOW; com o Jarvis escondido, é a janela do senhor
    monitor = display.get_monitor_at_window(ativa) if ativa is not None else None
    if monitor is None:
        _, x, y = display.get_default_seat().get_pointer().get_position()
        monitor = display.get_monitor_at_point(x, y)
    return next((i for i in range(display.get_n_monitors()) if display.get_monitor(i) == monitor), None)


def _carregar_depois(web: WebKit2.WebView, uri: str | None) -> bool:
    if uri:
        GLib.timeout_add(1000, lambda: web.load_uri(uri) and GLib.SOURCE_REMOVE)
    return True  # suprime a página de erro do WebKit


def _texto(resultado) -> str:
    return resultado.get_js_value().to_string() if hasattr(resultado, "get_js_value") else resultado.to_string()


class JanelaJarvis:
    def __init__(self, url: str, com_aviso: bool = True):
        self.janela = Gtk.Window(title="Jarvis")
        _janela_transparente(self.janela)
        self.janela.set_type_hint(Gdk.WindowTypeHint.NORMAL)
        self.janela.connect("delete-event", self._ao_fechar)
        self.web = _webview(self._ao_mensagem)
        self.janela.add(self.web)
        self.web.load_uri(url)
        self.web.show()
        self.aviso = self._criar_aviso(url) if com_aviso else None

        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, self.mostrar)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._sair)

    def mostrar(self, *_args) -> bool:
        if self.aviso is not None:
            self.aviso.hide()
        tela = self.janela.get_screen()
        indice = monitor_do_foco(tela)
        if indice is None:
            self.janela.fullscreen()
        else:
            self.janela.fullscreen_on_monitor(tela, indice)
        self.janela.show()
        self.janela.present_with_time(Gtk.get_current_event_time() or 0)
        self.web.grab_focus()
        self.web.evaluate_javascript("window.jarvis && window.jarvis.abrir()", -1, None, None, None, None, None)
        return GLib.SOURCE_CONTINUE

    def esconder(self) -> None:
        self.janela.hide()

    def _criar_aviso(self, url: str) -> Gtk.Window:
        """Faixa no canto da tela com a última fala, só quando a janela principal está fechada; nunca pega foco."""
        aviso = Gtk.Window(title="Jarvis — aviso")
        _janela_transparente(aviso)
        aviso.set_accept_focus(False)
        aviso.set_focus_on_map(False)
        aviso.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
        aviso.set_default_size(LARGURA_AVISO, ALTURA_AVISO)
        display = aviso.get_display()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        area = monitor.get_geometry()  # a tela X junta todos os monitores: o aviso fica no principal
        aviso.move(area.x + area.width - LARGURA_AVISO - 24, area.y + 24)
        web = _webview(self._ao_mensagem_aviso)
        aviso.add(web)
        web.load_uri(url.split("?", 1)[0].rstrip("/") + "/aviso.html")
        web.show()
        return aviso

    def _ao_mensagem(self, _gerente, resultado) -> None:
        if _texto(resultado) == "fechar":
            self.esconder()

    def _ao_mensagem_aviso(self, _gerente, resultado) -> None:
        valor = _texto(resultado)
        if valor == "mostrar_aviso" and not self.janela.get_visible():
            self.aviso.show()
        elif valor == "esconder_aviso":
            self.aviso.hide()

    def _ao_fechar(self, *_args) -> bool:
        self.esconder()
        return True

    def _sair(self, *_args) -> bool:
        Gtk.main_quit()
        return GLib.SOURCE_REMOVE


def main() -> None:
    parser = argparse.ArgumentParser(description="Janela do Jarvis")
    parser.add_argument("--url", default=URL_PADRAO)
    parser.add_argument("--mostrar", action="store_true", help="mostra a janela ao iniciar")
    args = parser.parse_args()

    (dados() / "hud.pid").write_text(str(os.getpid()))
    janela = JanelaJarvis(args.url, com_aviso=args.url.startswith("http"))
    if args.mostrar:
        GLib.timeout_add(400, lambda: janela.mostrar() and False)
    Gtk.main()


if __name__ == "__main__":
    main()
