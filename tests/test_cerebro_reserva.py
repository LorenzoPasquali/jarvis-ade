from jarvis import orca
from jarvis.cerebro import codex, reserva


def test_mensagem_traz_instrucoes_estado_conversa_e_pedido():
    historico = [{"papel": "usuario", "texto": "como está o portfólio?"},
                 {"papel": "jarvis", "texto": "Concluiu o deploy, senhor.\n\n🔊 Concluiu."}]
    m = reserva.mensagem("[voz] e o app de saúde?", historico, estado="• app-analise-saude [claude] concluiu")
    assert m.startswith(reserva.INSTRUCOES)
    assert "## Sessões de agentes abertas no Orca\n• app-analise-saude [claude] concluiu" in m
    assert "Senhor: como está o portfólio?\nJarvis: Concluiu o deploy, senhor. 🔊 Concluiu." in m
    assert m.endswith("## Mensagem atual\n[voz] e o app de saúde?")


def test_conversa_vazia_e_falas_longas_cortadas():
    assert "## Conversa recente com o senhor\n(nenhuma)" in reserva.mensagem("oi", [], estado="")
    longa = [{"papel": "jarvis", "texto": "x" * 5000}]
    assert "x" * (reserva.MAX_FALA + 1) not in reserva.mensagem("oi", longa, estado="")


def test_orca_fora_do_ar_vira_aviso(monkeypatch):
    def falha():
        raise orca.OrcaErro("runtime_unavailable", "Orca fechado")
    monkeypatch.setattr(orca, "agentes", falha)
    assert reserva.estado_orca() == "Orca indisponível: Orca fechado."


def test_codex_roda_somente_leitura_inclusive_ao_retomar(tmp_path):
    base = codex.comando_codex()
    assert base[:4] == ["codex", "-c", 'sandbox_mode="read-only"', "exec"]
    p = codex.ProcessoCodex(base, tmp_path, {}, lambda e: None, tmp_path / "s.json")
    assert "workspace-write" not in p.comando_atual("oi")
    (tmp_path / "s.json").write_text('{"thread_id": "t1"}')
    assert p.comando_atual("oi")[:6] == ["codex", "-c", 'sandbox_mode="read-only"', "exec", "resume", "t1"]
