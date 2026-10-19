import argparse
import sys
from collections.abc import Callable

Handler = Callable[[argparse.Namespace], int]


def _nao_implementado(_: argparse.Namespace) -> int:
    print("não implementado", file=sys.stderr)
    return 2


def _eventos(args: argparse.Namespace) -> int:
    from jarvis import eventos

    if args.seguir:
        for linha in eventos.seguir():
            print(linha, flush=True)
    print(eventos.pendentes())
    return 0


def _vigia(_: argparse.Namespace) -> int:
    from jarvis import vigia

    vigia.rodar()


def _status(args: argparse.Namespace) -> int:
    import json
    import time
    from dataclasses import asdict

    from jarvis import consultas, orca, sessao
    from jarvis.orca import OrcaErro

    try:
        agentes, terminais = orca.agentes(), orca.terminais()
    except OrcaErro as erro:
        print(f"{erro.mensagem} ({erro.codigo})")
        return 1
    jarvis = (sessao.ler() or {}).get("pane_key")
    if args.json:
        itens = [{**asdict(a), "terminal": getattr(terminais.get(a.pane_key), "handle", None)}
                 for a in agentes if a.pane_key != jarvis]
        print(json.dumps(itens, ensure_ascii=False, indent=2))
    else:
        print(consultas.formatar_status(agentes, terminais, jarvis, int(time.time() * 1000)))
    return 0


def _historico(args: argparse.Namespace) -> int:
    from datetime import datetime

    from jarvis import consultas, eventos, orca
    from jarvis.orca import OrcaErro

    agora = datetime.now().astimezone()
    try:
        desde = consultas.parse_periodo(args.desde, agora)
        repos = orca.executar(["repo", "list"]).get("repos", [])
    except ValueError as erro:
        print(erro)
        return 1
    except OrcaErro as erro:
        print(f"{erro.mensagem} ({erro.codigo})")
        return 1
    lidos, _ = eventos.ler_desde(0)
    no_periodo = [e for e in lidos if datetime.fromisoformat(e["em"]) >= desde]
    por_projeto = {r.get("displayName") or r["path"]: consultas.commits(r["path"], desde) for r in repos}
    print(consultas.formatar_historico(no_periodo, por_projeto, desde))
    return 0


def _clima(_: argparse.Namespace) -> int:
    from jarvis import consultas

    try:
        print(consultas.descrever_clima(consultas.buscar_clima()))
    except Exception:
        print("Não consegui consultar o clima agora.")
        return 1
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jarvis", description="Jarvis: orquestrador das sessões do Orca.")
    subs = parser.add_subparsers(dest="comando")

    def sub(nome: str, ajuda: str, handler: Handler = _nao_implementado) -> argparse.ArgumentParser:
        p = subs.add_parser(nome, help=ajuda)
        p.set_defaults(handler=handler)
        return p

    sub("iniciar", "abre a sessão do Jarvis neste terminal do Orca (padrão)")
    sub("status", "estado das sessões de agentes no Orca", _status).add_argument("--json", action="store_true")
    p = sub("eventos", "eventos registrados pelo vigia", _eventos)
    modo = p.add_mutually_exclusive_group()
    modo.add_argument("--pendentes", action="store_true", help="eventos desde a última leitura (padrão)")
    modo.add_argument("--seguir", action="store_true", help="fica ouvindo e imprime cada evento novo")
    sub("historico", "o que aconteceu nos projetos num período", _historico).add_argument(
        "--desde", default="1d", help="1d, 7d, 12h ou data ISO (padrão 1d)")
    sub("clima", "clima de agora em São Paulo", _clima)
    sub("enviar", "envia uma mensagem a um agente e registra a ação")
    sub("vigia", "loop que registra mudanças das sessões", _vigia)
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
