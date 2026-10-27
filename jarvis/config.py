import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
VOZ_URL = "http://127.0.0.1:8765"
VOZ_PORTA = 8765
OMNIVOICE_PY = Path("/git/FERRAMENTAS-LOCAL/OmniVoice/.venv/bin/python")
MP3_REFERENCIA = RAIZ / "JarvisExample.mp3"
TEXTO_REFERENCIA = (
    "Olá, senhor! Hoje estão fazendo 20 graus. O clima está propenso. "
    "Dos seus últimos projetos do ORCA, o que mais precisa ser revisado é o modelo de gestão de saúde."
)


def dados() -> Path:
    """Diretório de runtime (eventos, ações, estado). `JARVIS_DADOS` sobrescreve, para testes."""
    caminho = Path(os.environ.get("JARVIS_DADOS", RAIZ / "dados"))
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho

# Em dados/: a voz continua muda depois de reiniciar a voz ou o computador (o servidor de voz grava; o cérebro lê).
MARCA_MUDO = "mudo"

# Frases que o servidor de voz deixa geradas de antemão, para tocar sem esperar a síntese.
SAUDACAO = "Como posso ajudar, senhor?"


def frase_pronta(nome: str) -> Path:
    return dados() / "voz" / "frases" / f"{nome}.wav"
