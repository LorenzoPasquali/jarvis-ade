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


class JanelaJarvis:
    def __init__(self, url: str):
        self.janela = Gtk.Window(title="Jarvis")
        self.janela.set_decorated(False)
        self.janela.set_keep_above(True)
        self.janela.set_skip_taskbar_hint(True)
        self.janela.set_skip_pager_hint(True)
        self.janela.set_type_hint(Gdk.WindowTypeHint.NORMAL)
        visual = self.janela.get_screen().get_rgba_visual()
        if visual is not None:
            self.janela.set_visual(visual)
        self.janela.set_app_paintable(True)
        self.janela.connect("delete-event", self._ao_fechar)

        conteudo = WebKit2.UserContentManager()
        conteudo.register_script_message_handler("jarvis")
        conteudo.connect("script-message-received::jarvis", self._ao_mensagem)
        self.web = WebKit2.WebView.new_with_user_content_manager(conteudo)
        self.web.set_background_color(Gdk.RGBA(0, 0, 0, 0))
        self.web.get_settings().set_enable_developer_extras(False)
        self.janela.add(self.web)
        self.web.load_uri(url)
        self.web.show()

        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, self.mostrar)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._sair)

    def mostrar(self, *_args) -> bool:
        self.janela.fullscreen()
        self.janela.show()
        self.janela.present_with_time(Gtk.get_current_event_time() or 0)
        self.web.grab_focus()
        self.web.evaluate_javascript("window.jarvis && window.jarvis.abrir()", -1, None, None, None, None, None)
        return GLib.SOURCE_CONTINUE

    def esconder(self) -> None:
        self.janela.hide()

    def _ao_mensagem(self, _gerente, resultado) -> None:
        valor = resultado.get_js_value().to_string() if hasattr(resultado, "get_js_value") else resultado.to_string()
        if valor == "fechar":
            self.esconder()

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
    janela = JanelaJarvis(args.url)
    if args.mostrar:
        GLib.timeout_add(400, lambda: janela.mostrar() and False)
    Gtk.main()


if __name__ == "__main__":
    main()
