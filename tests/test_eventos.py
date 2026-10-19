from jarvis import eventos


def ev(i: int, tipo: str = "terminou", resumo: str = "feito") -> dict:
    return {"id": str(i), "em": "2026-10-19T12:00:00", "tipo": tipo, "projeto": "app-analise-saude",
            "worktree": "app-analise-saude", "caminho": "/git/app-analise-saude", "pane_key": "S",
            "agente": "claude", "estado": "done", "resumo": resumo}


def test_anexar_e_ler_em_ordem(dados_tmp):
    eventos.anexar(ev(1))
    eventos.anexar(ev(2))
    lidos, offset = eventos.ler_desde(0)
    assert [e["id"] for e in lidos] == ["1", "2"]
    eventos.anexar(ev(3))
    novos, _ = eventos.ler_desde(offset)
    assert [e["id"] for e in novos] == ["3"]


def test_ler_sem_arquivo(dados_tmp):
    assert eventos.ler_desde(0) == ([], 0)


def test_pendentes_avanca_cursor(dados_tmp):
    eventos.anexar(ev(1))
    assert "app-analise-saude" in eventos.pendentes()
    assert eventos.pendentes() == "Nenhum evento novo."


def test_pendentes_limita(dados_tmp):
    for i in range(35):
        eventos.anexar(ev(i))
    saida = eventos.pendentes()
    assert "… e mais 5 eventos anteriores" in saida
    assert saida.count("[evento]") == 30


def test_formatar_aguardando():
    linha = eventos.formatar(ev(1, tipo="aguardando", resumo="Posso seguir com o plano 4?"))
    assert linha.startswith("[evento] app-analise-saude:") and "«Posso seguir com o plano 4?»" in linha


def test_seguir_comeca_no_fim_e_avanca_cursor(dados_tmp):
    eventos.anexar(ev(1))
    gerador = eventos.seguir(intervalo=0.01)
    eventos.anexar(ev(2))
    linha = next(gerador)
    assert "[evento]" in linha
    assert eventos.pendentes() == "Nenhum evento novo."
