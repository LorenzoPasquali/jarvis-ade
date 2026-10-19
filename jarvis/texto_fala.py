"""Prepara o texto das respostas para a voz: escolhe o trecho falável, limpa e divide em frases.

Só stdlib: também é importado pelo servidor de voz, que roda no venv do OmniVoice.
"""

import re

MARCADOR = "🔊"
_ABREVIACOES = {"sr", "sra", "srta", "dr", "dra", "prof", "profa", "etc", "ex", "obs", "nº", "n"}
_MIN_FRASE = 25

_BLOCO_CODIGO = re.compile(r"```.*?(```|$)", re.S)
_CODIGO_INLINE = re.compile(r"`[^`\n]*`")
_URL = re.compile(r"(https?://|www\.)\S+?(?=[.,;:!?)\]]*(\s|$))")
_CAMINHO = re.compile(r"(?<![\w/])~?/[\w.\-]+(/[\w.\-]*)+")
_HANDLE = re.compile(r"\bterm_[\w-]+")
_FIM_FRASE = re.compile(r"[.!?…]+(?=\s)")


def limpar_para_fala(texto: str) -> str:
    texto = _BLOCO_CODIGO.sub(" ", texto)
    linhas = []
    for linha in texto.splitlines():
        if linha.lstrip().startswith("|"):
            continue
        linha = re.sub(r"^\s*(#+|>+)\s*", "", linha)
        linha = re.sub(r"^\s*([-*•+]|\d+[.)])\s+", "", linha)
        linhas.append(linha)
    texto = " ".join(linhas)
    texto = _CODIGO_INLINE.sub(" ", texto)
    texto = _URL.sub(" ", texto)
    texto = _CAMINHO.sub(" ", texto)
    texto = _HANDLE.sub(" ", texto)
    texto = re.sub(r"\*+|(?<!\w)_+|_+(?!\w)", "", texto)
    texto = re.sub(r"\s+", " ", texto)
    texto = re.sub(r"\s+([.,;:!?…])", r"\1", texto)
    return texto.strip()


def _sentencas(texto: str) -> list[str]:
    partes, inicio = [], 0
    for m in _FIM_FRASE.finditer(texto):
        anterior = re.search(r"(\w+)$", texto[inicio:m.start()])
        if m.group() == "." and anterior and anterior.group(1).casefold() in _ABREVIACOES:
            continue
        partes.append(texto[inicio:m.end()].strip())
        inicio = m.end()
    resto = texto[inicio:].strip()
    if resto:
        partes.append(resto)
    return [p for p in partes if p]


def _cortar(texto: str, max_chars: int) -> str:
    if len(texto) <= max_chars:
        return texto
    corte = texto[:max_chars + 1]
    corte = corte[:corte.rfind(" ")] if " " in corte else corte[:max_chars]
    return corte.rstrip(" ,;:")


def extrair_fala(mensagem: str, max_chars: int = 400) -> str:
    marcadas = [linha.strip()[len(MARCADOR):] for linha in mensagem.splitlines()
                if linha.strip().startswith(MARCADOR)]
    if marcadas:
        texto = limpar_para_fala(" ".join(marcadas))
    else:
        texto = " ".join(_sentencas(limpar_para_fala(mensagem))[:2])
    return _cortar(texto, max_chars)


def _quebrar_longa(frase: str, max_chars: int) -> list[str]:
    pedacos, atual = [], ""
    for trecho in re.split(r"(?<=[,;])\s+", frase):
        candidato = f"{atual} {trecho}".strip()
        if len(candidato) <= max_chars:
            atual = candidato
            continue
        if atual:
            pedacos.append(atual)
        while len(trecho) > max_chars:
            parte = _cortar(trecho, max_chars)
            pedacos.append(parte)
            trecho = trecho[len(parte):].strip()
        atual = trecho
    if atual:
        pedacos.append(atual)
    return pedacos


def dividir_frases(texto: str, max_chars: int = 220) -> list[str]:
    partes = []
    for frase in _sentencas(re.sub(r"\s+", " ", texto).strip()):
        partes += _quebrar_longa(frase, max_chars) if len(frase) > max_chars else [frase]
    frases, pendente = [], ""
    for parte in partes:
        atual = f"{pendente} {parte}".strip()
        if len(atual) > max_chars:
            frases.append(pendente)
            atual = parte
        if len(atual) < _MIN_FRASE:
            pendente = atual
            continue
        frases.append(atual)
        pendente = ""
    if pendente:
        if frases and len(frases[-1]) + 1 + len(pendente) <= max_chars:
            frases[-1] = f"{frases[-1]} {pendente}"
        else:
            frases.append(pendente)
    return frases
