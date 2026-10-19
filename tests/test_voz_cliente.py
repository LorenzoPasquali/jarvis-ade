import json

import pytest

from conftest import ag
from jarvis import sessao
from jarvis.orca import OrcaErro
from jarvis.voz_cliente import calar, hook_fala, mudo, ouvir, transcricao_util


class GravadorFalso:
    def __init__(self, duracao: float = 2.0):
        self.duracao, self.ativos = duracao, set()

    def iniciar(self, caminho) -> int:
        self.ativos.add(4242)
        return 4242

    def ativo(self, pid: int) -> bool:
        return pid in self.ativos

    def encerrar(self, pid: int) -> float:
        self.ativos.discard(pid)
        return self.duracao


def chamar_falso(respostas: dict, rotas: list | None = None):
    def chamar(rota, corpo=None, **kwargs):
        if rotas is not None:
            rotas.append(rota)
        return respostas.get(rota, {})
    return chamar


def nada(_):
    pass


def jarvis_vivo(estado="done"):
    return lambda: [ag("J", estado, projeto="jarvis")]


def test_hook_fala_envia_linha_marcada():
    chamadas = []
    hook_fala(json.dumps({"last_assistant_message": "texto\n🔊 Pronto, senhor."}),
              chamar=lambda r, c=None, **k: chamadas.append((r, c)))
    assert chamadas == [("/falar", {"texto": "Pronto, senhor."})]


def test_hook_fala_sem_texto_falavel_nao_chama():
    chamadas = []
    hook_fala(json.dumps({"last_assistant_message": "```\nls\n```"}), chamar=lambda *a, **k: chamadas.append(a))
    assert chamadas == []


def test_hook_fala_nunca_levanta(dados_tmp):
    hook_fala("não é json", chamar=lambda *a, **k: None)
    hook_fala(json.dumps({"last_assistant_message": "🔊 Oi, senhor."}), chamar=lambda *a, **k: 1 / 0)
    assert (dados_tmp / "hook.log").exists()


@pytest.mark.parametrize("texto,dur,esperado", [
    ("Legendas pela comunidade Amara.org", 3.0, None),
    ("Legenda por Sônia Ruberti", 3.0, None),
    ("Legendas pela comunidade Amara.org. Obrigado.", 3.0, None),
    ("Tchau, tchau.", 2.0, None),
    ("Obrigado.", 2.0, None),
    ("...", 2.0, None),
    ("", 2.0, None),
    ("status dos projetos", 0.3, None),
    ("Jarvis, como estão os projetos?", 2.0, "Jarvis, como estão os projetos?"),
])
def test_transcricao_util(texto, dur, esperado):
    assert transcricao_util(texto, dur) == esperado


def test_ouvir_alterna_e_envia(dados_tmp):
    sessao.registrar("J", "term_j")
    grav, envios = GravadorFalso(duracao=2.0), []
    chamar = chamar_falso({"/transcrever": {"texto": "como estão os projetos"}})

    def executar(args, **k):
        envios.append(args)
        return {}

    assert ouvir(grav, chamar=chamar, executar=executar, notificar=nada, obter_agentes=jarvis_vivo()) == "gravando"
    assert ouvir(grav, chamar=chamar, executar=executar, notificar=nada, obter_agentes=jarvis_vivo()) == "enviado"
    assert envios[0][:4] == ["terminal", "send", "--terminal", "term_j"]
    assert "[voz] como estão os projetos" in envios[0] and envios[0][-1] == "--enter"


def test_ouvir_para_fala_ao_comecar(dados_tmp):
    rotas = []
    ouvir(GravadorFalso(), chamar=chamar_falso({}, rotas), executar=None, notificar=nada)
    assert rotas[0] == "/parar"


def test_ouvir_descarta_alucinacao(dados_tmp):
    sessao.registrar("J", "term_j")
    grav = GravadorFalso(duracao=2.0)
    chamar = chamar_falso({"/transcrever": {"texto": "Obrigado."}})
    ouvir(grav, chamar=chamar, executar=None, notificar=nada)
    assert ouvir(grav, chamar=chamar, executar=lambda *a, **k: pytest.fail("não deveria enviar"),
                 notificar=nada) == "descartado"


def test_ouvir_sem_sessao(dados_tmp):
    grav = GravadorFalso()
    chamar = chamar_falso({"/transcrever": {"texto": "como estão os projetos"}})
    ouvir(grav, chamar=chamar, executar=None, notificar=nada)
    assert ouvir(grav, chamar=chamar, executar=None, notificar=nada) == "sem_sessao"


def test_ouvir_envio_falha_vira_sem_sessao(dados_tmp):
    sessao.registrar("J", "term_j")
    grav = GravadorFalso()
    chamar = chamar_falso({"/transcrever": {"texto": "como estão os projetos"}})

    def falha(args, **k):
        raise OrcaErro("terminal_not_found", "x")

    ouvir(grav, chamar=chamar, executar=falha, notificar=nada, obter_agentes=jarvis_vivo())
    assert ouvir(grav, chamar=chamar, executar=falha, notificar=nada, obter_agentes=jarvis_vivo()) == "sem_sessao"


def test_ouvir_sem_servidor_de_voz(dados_tmp):
    avisos = []
    assert ouvir(GravadorFalso(), chamar=lambda *a, **k: None, executar=None, notificar=avisos.append) == "sem_voz"
    assert avisos == ["Servidor de voz indisponível."]


def test_calar_e_mudo():
    rotas = []
    chamar = lambda r, c=None, **k: rotas.append((r, c)) or {}
    calar(chamar=chamar)
    mudo(True, chamar=chamar)
    assert rotas == [("/parar", None), ("/mudo", {"ligado": True})]


def test_ouvir_sessao_registrada_mas_fechada(dados_tmp):
    sessao.registrar("J", "term_j")
    grav = GravadorFalso()
    chamar = chamar_falso({"/transcrever": {"texto": "como estão os projetos"}})
    ouvir(grav, chamar=chamar, executar=None, notificar=nada)
    assert ouvir(grav, chamar=chamar, executar=lambda *a, **k: pytest.fail("terminal já não é do Jarvis"),
                 notificar=nada, obter_agentes=lambda: [ag("X", "working")]) == "sem_sessao"


def test_ouvir_nao_envia_enter_com_jarvis_em_permissao(dados_tmp):
    sessao.registrar("J", "term_j")
    grav, avisos = GravadorFalso(), []
    chamar = chamar_falso({"/transcrever": {"texto": "pode seguir"}})
    ouvir(grav, chamar=chamar, executar=None, notificar=nada)
    assert ouvir(grav, chamar=chamar, executar=lambda *a, **k: pytest.fail("Enter aprovaria a permissão"),
                 notificar=avisos.append, obter_agentes=jarvis_vivo("permission")) == "jarvis_ocupado"
    assert "permissão" in avisos[-1]


def test_ouvir_segura_a_fala_durante_a_gravacao(dados_tmp):
    sessao.registrar("J", "term_j")
    grav, rotas = GravadorFalso(), []
    chamar = chamar_falso({"/transcrever": {"texto": "como estão os projetos"}}, rotas)
    ouvir(grav, chamar=chamar, executar=None, notificar=nada)
    assert rotas[:2] == ["/parar", "/ouvindo"]
    ouvir(grav, chamar=chamar, executar=lambda *a, **k: {}, notificar=nada, obter_agentes=jarvis_vivo())
    assert rotas[-1] == "/ouvindo" and rotas.index("/transcrever") < len(rotas) - 1


def test_hook_avisa_quando_voz_cai(dados_tmp):
    avisos = []
    hook_fala(json.dumps({"last_assistant_message": "🔊 Oi, senhor."}), chamar=lambda *a, **k: None,
              notificar=avisos.append)
    hook_fala(json.dumps({"last_assistant_message": "🔊 De novo."}), chamar=lambda *a, **k: None,
              notificar=avisos.append)
    assert avisos == ["Voz do Jarvis indisponível; respostas só em texto."]
    assert "indisponível" in (dados_tmp / "hook.log").read_text()


def test_hook_respeita_silencio():
    chamadas = []
    hook_fala(json.dumps({"last_assistant_message": "Monitor rearmado.\n🔇"}),
              chamar=lambda *a, **k: chamadas.append(a))
    assert chamadas == []
