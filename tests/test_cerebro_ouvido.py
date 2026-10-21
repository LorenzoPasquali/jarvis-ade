import sys
import time

from jarvis.cerebro import main as cerebro_main
from jarvis.cerebro import ouvido as ouvido_mod
from jarvis.cerebro.main import Cerebro
from jarvis.config import frase_pronta


class DetectorFalso:
    """Detecta a palavra no 3º quadro."""
    frame_length = 4
    sample_rate = 16000

    def __init__(self):
        self.quadros = 0
        self.apagado = False

    def process(self, quadro):
        self.quadros += 1
        assert len(quadro) == self.frame_length
        return 0 if self.quadros == 3 else -1

    def delete(self):
        self.apagado = True


def esperar(cond, limite=5.0):
    fim = time.time() + limite
    while time.time() < fim:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_sem_chave_o_ouvido_fica_desligado(monkeypatch, tmp_path):
    monkeypatch.delenv("PICOVOICE_ACCESS_KEY", raising=False)
    monkeypatch.setattr(ouvido_mod, "ARQUIVO_CHAVE", tmp_path / "nao-existe.key")
    criados = []
    o = ouvido_mod.Ouvido(lambda: None, criar_detector=lambda: criados.append(1))
    assert o.iniciar() is False
    assert criados == []


def test_chave_vem_do_arquivo_fora_do_repositorio(monkeypatch, tmp_path):
    monkeypatch.delenv("PICOVOICE_ACCESS_KEY", raising=False)
    (tmp_path / "picovoice.key").write_text("  abc123\n")
    monkeypatch.setattr(ouvido_mod, "ARQUIVO_CHAVE", tmp_path / "picovoice.key")
    assert ouvido_mod.chave() == "abc123"


def test_palavra_detectada_chama_o_cerebro(monkeypatch):
    monkeypatch.setenv("PICOVOICE_ACCESS_KEY", "teste")
    ouvidas = []
    detector = DetectorFalso()
    # 8 bytes por quadro (4 amostras s16); o "gravador" manda zeros para sempre
    gravador = [sys.executable, "-c", "import sys,time\nwhile True: sys.stdout.buffer.write(bytes(8)); "
                                      "sys.stdout.flush(); time.sleep(0.01)"]
    o = ouvido_mod.Ouvido(lambda: ouvidas.append(1), criar_detector=lambda: detector, comando=gravador)
    assert o.iniciar()
    assert esperar(lambda: ouvidas == [1])
    o.parar()
    assert esperar(lambda: detector.apagado)


def _cerebro(dados_tmp, saude=None):
    chamadas, tocadas, janelas = [], [], []

    def voz(rota, corpo=None, **_):
        chamadas.append(rota)
        return saude if rota == "/saude" else {}
    c = Cerebro(claude=None, falar=lambda t: True, bloqueada=lambda: False, chamar_voz=voz)
    c.tocar = tocadas.append
    c.mostrar_janela = lambda: janelas.append(1)
    iniciadas = []
    c.escuta.iniciar = lambda: iniciadas.append(1)
    return c, chamadas, tocadas, janelas, iniciadas


def test_jarvis_cala_cumprimenta_e_abre_ouvindo(dados_tmp):
    saudacao = frase_pronta("saudacao")
    saudacao.parent.mkdir(parents=True, exist_ok=True)
    saudacao.write_bytes(b"RIFF")
    c, chamadas, tocadas, janelas, iniciadas = _cerebro(dados_tmp, saude={"mudo": False})
    c.palavra_jarvis()
    assert chamadas[0] == "/parar"
    assert tocadas == [saudacao] and janelas == [1] and iniciadas == [1]
    assert c._estado == "ouvindo"
    c.palavra_jarvis()  # eco/repetição logo em seguida: ignora
    assert tocadas == [saudacao]


def test_jarvis_mudo_ou_sem_frase_pronta_so_abre(dados_tmp):
    c, _, tocadas, janelas, iniciadas = _cerebro(dados_tmp, saude={"mudo": True})
    frase = frase_pronta("saudacao")
    frase.parent.mkdir(parents=True, exist_ok=True)
    frase.write_bytes(b"RIFF")
    c.palavra_jarvis()
    assert tocadas == [] and janelas == [1] and iniciadas == [1]
    frase.unlink()
    c2, _, tocadas2, _, _ = _cerebro(dados_tmp, saude={})
    c2.palavra_jarvis()
    assert tocadas2 == []


def test_jarvis_ignorado_enquanto_fala_ou_ja_ouve(dados_tmp):
    c, _, tocadas, janelas, _ = _cerebro(dados_tmp, saude={})
    c._estado = "falando"
    c.palavra_jarvis()
    c._estado = "ocioso"
    c.escuta.ativa = True
    c.palavra_jarvis()
    assert janelas == []


def test_ferramentas_viram_progresso_em_texto(dados_tmp):
    c, *_ = _cerebro(dados_tmp, saude={})
    publicados = []
    c.publicar = publicados.append
    c.ao_evento_claude({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "Vou ver."},
        {"type": "tool_use", "name": "Bash", "input": {"command": "jarvis projetos --todos"}},
        {"type": "tool_use", "name": "WebSearch", "input": {"query": "notícias IA hoje"}},
    ]}})
    assert [p["texto"] for p in publicados if p["tipo"] == "progresso"] == [
        "Consultando os projetos…", "Pesquisando na web: notícias IA hoje"]
    assert cerebro_main.descrever_ferramenta("Bash", {"command": "ls -la /git"}) == "Rodando: ls -la /git"
