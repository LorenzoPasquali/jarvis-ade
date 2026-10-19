from jarvis.texto_fala import dividir_frases, extrair_fala, limpar_para_fala


def test_extrai_linha_marcada():
    msg = "| proj | estado |\n|---|---|\n\n🔊 Pronto, senhor. Duas sessões ativas."
    assert extrair_fala(msg) == "Pronto, senhor. Duas sessões ativas."


def test_extrai_varias_linhas_marcadas_e_limpa():
    msg = "detalhes\n🔊 Senhor, o `app` terminou.\n🔊 Veja https://x.y/z agora."
    assert extrair_fala(msg) == "Senhor, o terminou. Veja agora."


def test_sem_marcador_usa_duas_frases_limpas():
    msg = "Veja `orca worktree ps`. O app terminou em /git/app. Detalhes em https://x.y. Mais uma frase."
    f = extrair_fala(msg)
    assert "`" not in f and "https" not in f and "/git/app" not in f
    assert f.count(".") <= 2


def test_mensagem_so_codigo_fica_vazia():
    assert extrair_fala("```bash\nls -la\n```") == ""


def test_corta_no_limite_em_fim_de_palavra():
    f = extrair_fala("🔊 " + "palavra " * 100, max_chars=50)
    assert len(f) <= 50 and not f.endswith(" ") and f.split()[-1] == "palavra"


def test_limpar_remove_markdown_tabela_e_handles():
    texto = "## Título\n**negrito** e _itálico_\n- item um\n| a | b |\nterminal term_abc123 pronto"
    limpo = limpar_para_fala(texto)
    assert "#" not in limpo and "*" not in limpo and "|" not in limpo and "term_abc123" not in limpo
    assert "negrito" in limpo and "item um" in limpo


def test_dividir_frases_respeita_abreviacoes_e_decimais():
    assert dividir_frases("Olá, Sr. Lorenzo, a nota é 9.5 hoje. Pronto!") == ["Olá, Sr. Lorenzo, a nota é 9.5 hoje. Pronto!"]
    partes = dividir_frases("Primeira frase bem completa aqui. Segunda frase também completa aqui.")
    assert partes == ["Primeira frase bem completa aqui.", "Segunda frase também completa aqui."]


def test_frase_longa_quebra_em_virgula():
    longa = ", ".join(["trecho número %d da frase" % i for i in range(20)]) + "."
    partes = dividir_frases(longa)
    assert len(partes) > 1 and all(len(p) <= 220 for p in partes)


def test_dividir_vazio():
    assert dividir_frases("   ") == []


def test_juncao_de_frase_curta_nao_passa_do_limite():
    longa = "palavra " * 26 + "fim."
    partes = dividir_frases("Sim, senhor. " + longa.strip(), max_chars=220)
    assert all(len(p) <= 220 for p in partes)
