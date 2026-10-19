import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from voz.servidor import Locutor, criar_servidor


def esperar(condicao, limite=3.0):
    fim = time.time() + limite
    while time.time() < fim:
        if condicao():
            return
        time.sleep(0.02)
    raise AssertionError("condição não atingida")


class MotorFalso:
    def sintetizar(self, frase: str) -> bytes:
        return frase.encode()


class TocadorFalso:
    def __init__(self, duracao: float = 0.0):
        self.duracao, self.tocados, self.parados = duracao, [], 0
        self._interromper = threading.Event()

    def tocar(self, wav: bytes) -> None:
        self._interromper.clear()
        self.tocados.append(wav)
        self._interromper.wait(self.duracao)

    def parar(self) -> None:
        self.parados += 1
        self._interromper.set()


class TranscritorFalso:
    def transcrever(self, caminho: str) -> str:
        return "texto falso"


def test_falar_toca_frases_em_ordem():
    toc = TocadorFalso()
    loc = Locutor(MotorFalso(), toc)
    loc.falar("Primeira frase bem completa aqui. Segunda frase também completa aqui.")
    esperar(lambda: len(toc.tocados) == 2)
    assert toc.tocados == ["Primeira frase bem completa aqui.".encode(), "Segunda frase também completa aqui.".encode()]


def test_parar_descarta_fila_e_geradas():
    toc = TocadorFalso(duracao=0.5)
    loc = Locutor(MotorFalso(), toc)
    loc.falar("Frase um longa o bastante. Frase dois longa o bastante. Frase três longa o bastante.")
    esperar(lambda: len(toc.tocados) == 1)
    loc.parar()
    time.sleep(0.8)
    assert len(toc.tocados) == 1 and toc.parados >= 1 and loc.estado()["fila"] == 0


def test_fala_depois_de_parar_funciona():
    toc = TocadorFalso()
    loc = Locutor(MotorFalso(), toc)
    loc.parar()
    loc.falar("Depois de parar ainda fala normalmente.")
    esperar(lambda: len(toc.tocados) == 1)


def test_mudo_ignora_fala():
    toc = TocadorFalso()
    loc = Locutor(MotorFalso(), toc)
    loc.mudo = True
    loc.falar("Teste de fala qualquer.")
    time.sleep(0.3)
    assert toc.tocados == []


@pytest.fixture
def servidor_falso():
    loc = Locutor(MotorFalso(), TocadorFalso())
    srv = criar_servidor(loc, TranscritorFalso(), porta=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def post(base, rota, corpo):
    dados = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()
    req = urllib.request.Request(base + rota, data=dados, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {}


def test_http_rotas(servidor_falso):
    assert post(servidor_falso, "/falar", {"texto": "Olá, senhor."})[0] == 202
    with urllib.request.urlopen(servidor_falso + "/saude", timeout=3) as r:
        assert json.loads(r.read())["ok"] is True
    assert post(servidor_falso, "/transcrever", {"caminho": "/tmp/x.wav"}) == (200, {"texto": "texto falso"})
    assert post(servidor_falso, "/mudo", {"ligado": True})[0] == 200
    assert post(servidor_falso, "/parar", {})[0] == 200
    assert post(servidor_falso, "/falar", b"nao-json")[0] == 400
    assert post(servidor_falso, "/inexistente", {})[0] == 404
