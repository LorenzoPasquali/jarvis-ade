import argparse
import sys
from collections.abc import Callable

Handler = Callable[[argparse.Namespace], int]


def _nao_implementado(_: argparse.Namespace) -> int:
    print("não implementado", file=sys.stderr)
    return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jarvis", description="Jarvis: orquestrador das sessões do Orca.")
    subs = parser.add_subparsers(dest="comando")

    def sub(nome: str, ajuda: str, handler: Handler = _nao_implementado) -> argparse.ArgumentParser:
        p = subs.add_parser(nome, help=ajuda)
        p.set_defaults(handler=handler)
        return p

    sub("iniciar", "abre a sessão do Jarvis neste terminal do Orca (padrão)")
    sub("status", "estado das sessões de agentes no Orca")
    sub("eventos", "eventos registrados pelo vigia")
    sub("historico", "o que aconteceu nos projetos num período")
    sub("clima", "clima de agora em São Paulo")
    sub("enviar", "envia uma mensagem a um agente e registra a ação")
    sub("vigia", "loop que registra mudanças das sessões")
    sub("hook-fala", "hook Stop: fala a resposta do Jarvis")
    sub("ouvir", "aperta-e-fala: começa ou termina a gravação")
    sub("calar", "interrompe a fala")
    sub("mudo", "liga ou desliga o modo mudo")
    sub("instalar", "instala serviços, atalhos e o comando jarvis")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = _parser().parse_args(argv or ["iniciar"])
    return args.handler(args)
