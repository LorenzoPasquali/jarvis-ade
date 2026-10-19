from jarvis.cerebro.fala import SeparadorFala


def test_separador_fala_linha_a_linha():
    falas = []
    s = SeparadorFala(falas.append)
    for d in ["Texto ", "longo.\n🔊 Pron", "to, senhor.\n🔊 Duas ", "sessões."]:
        s.alimentar(d)
    assert falas == ["Pronto, senhor."]
    s.fim("Texto longo.\n🔊 Pronto, senhor.\n🔊 Duas sessões.")
    assert falas == ["Pronto, senhor.", "Duas sessões."]


def test_separador_sem_marcador_usa_resumo():
    falas = []
    s = SeparadorFala(falas.append)
    s.alimentar("O app terminou. Tudo certo.")
    s.fim("O app terminou. Tudo certo.")
    assert falas == ["O app terminou. Tudo certo."]


def test_separador_silencio():
    falas = []
    s = SeparadorFala(falas.append)
    s.alimentar("Monitor ok.\n🔇")
    s.fim("Monitor ok.\n🔇")
    assert falas == []


def test_reiniciar_limpa_estado():
    falas = []
    s = SeparadorFala(falas.append)
    s.alimentar("🔊 Meia fra")
    s.reiniciar()
    s.alimentar("Outra resposta.")
    s.fim("Outra resposta.")
    assert falas == ["Outra resposta."]
