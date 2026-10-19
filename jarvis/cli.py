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


def _enviar(args: argparse.Namespace) -> int:
    from jarvis import enviar, orca, sessao
    from jarvis.orca import OrcaErro

    try:
        destino = enviar.resolver_destino(args.projeto, args.terminal, orca.agentes(), orca.terminais(),
                                          sessao.ler())
        if args.origem == "voz":
            from jarvis import pendencias

            if args.texto is None:
                print("Ordem falada precisa de --texto.")
                return 1
            alvo = destino.projeto or destino.caminho
            p = pendencias.criar("enviar", f"Para **{alvo}**: «{args.texto}»",
                                 {"terminal": destino.terminal, "pane_key": destino.pane_key,
                                  "projeto": destino.projeto, "caminho": destino.caminho, "texto": args.texto})
            print(f"Aguardando confirmação do senhor (pendência {p['id']}): enviar a {alvo}: «{args.texto}»")
            return 0
        enviar.enviar(destino, texto=args.texto, tecla=args.tecla, origem=args.origem, motivo=args.motivo,
                      confirmado=False)
    except enviar.EnvioRecusado as recusa:
        print(recusa)
        return 1
    except OrcaErro as erro:
        print(f"Falhou ao enviar: {erro.mensagem} ({erro.codigo})")
        return 1
    print(f"Enviado para {destino.projeto or destino.caminho} ({destino.terminal}).")
    return 0


def _hook_fala(_: argparse.Namespace) -> int:
    from jarvis import voz_cliente

    voz_cliente.hook_fala(sys.stdin.read())
    return 0


def _ouvir(_: argparse.Namespace) -> int:
    from jarvis import voz_cliente

    print(voz_cliente.ouvir(voz_cliente.GravadorPw()))
    return 0


def _calar(_: argparse.Namespace) -> int:
    from jarvis import voz_cliente

    voz_cliente.calar()
    return 0


def _mudo(args: argparse.Namespace) -> int:
    from jarvis import voz_cliente

    voz_cliente.mudo(args.estado == "on")
    print("Modo mudo ligado." if args.estado == "on" else "Modo mudo desligado.")
    return 0


def _iniciar(_: argparse.Namespace) -> int:
    from jarvis import lancador

    return lancador.iniciar()


def _instalar(_: argparse.Namespace) -> int:
    from jarvis import lancador

    return lancador.instalar()


def _hud(args: argparse.Namespace) -> int:
    from jarvis import hud_cli

    return hud_cli.hud(demo=args.demo)


def _lancar(args: argparse.Namespace) -> int:
    from jarvis import lancar, orca, pendencias
    from jarvis.orca import OrcaErro

    try:
        plano = lancar.planejar(args.projeto, args.tarefa, orca.agentes(), orca.executar(["repo", "list"])["repos"])
        if plano["acao"] == "perguntar":
            print(plano["motivo"])
            return 1
        if args.origem == "voz":
            alvo = plano.get("projeto") or plano.get("caminho")
            verbo = "Mandar ao agente de" if plano["acao"] == "enviar" else "Abrir um agente em"
            p = pendencias.criar("lancar", f"{verbo} **{alvo}**: «{args.tarefa}»", plano)
            print(f"Aguardando confirmação do senhor (pendência {p['id']}): {verbo.lower()} {alvo}.")
            return 0
        print(lancar.executar_plano(plano, origem="texto"))
    except (ValueError, OrcaErro) as erro:
        print(erro)
        return 1
    return 0


def _regra(args: argparse.Namespace) -> int:
    from jarvis import pendencias

    if args.acao == "adicionar":
        texto = " ".join(args.texto).strip()
        if not texto:
            print("Diga a regra.")
            return 1
        p = pendencias.criar("regra", f"Nova regra: «{texto}»", {"texto": texto})
        print(f"Aguardando confirmação do senhor (pendência {p['id']}): nova regra «{texto}».")
        return 0
    try:
        print(pendencias.remover_regra(int(args.texto[0])))
    except (ValueError, IndexError):
        print("Informe o número da regra a remover.")
        return 1
    return 0


def _decidir(args: argparse.Namespace) -> int:
    from jarvis import pendencias

    try:
        p = pendencias.confirmar(args.id) if args.comando == "confirmar" else pendencias.recusar(args.id)
    except ValueError as erro:
        print(erro)
        return 1
    print(p["resultado"] or f"Pendência {p['id']}: {p['estado']}.")
    return 0 if p["estado"] in ("executada", "recusada") else 1


def _pendencias(_: argparse.Namespace) -> int:
    from jarvis import pendencias

    abertas = pendencias.listar()
    for p in abertas:
        print(f"{p['id']}: {p['descricao']}")
    if not abertas:
        print("Nenhuma pendência aberta.")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jarvis", description="Jarvis: orquestrador das sessões do Orca.")
    subs = parser.add_subparsers(dest="comando")

    def sub(nome: str, ajuda: str, handler: Handler = _nao_implementado) -> argparse.ArgumentParser:
        p = subs.add_parser(nome, help=ajuda)
        p.set_defaults(handler=handler)
        return p

    sub("iniciar", "abre a sessão do Jarvis neste terminal do Orca (padrão)", _iniciar)
    sub("hud", "abre a janela do Jarvis e começa a ouvir (Super+J)", _hud).add_argument(
        "--demo", action="store_true", help="dados de exemplo, sem o cérebro")
    sub("status", "estado das sessões de agentes no Orca", _status).add_argument("--json", action="store_true")
    p = sub("eventos", "eventos registrados pelo vigia", _eventos)
    modo = p.add_mutually_exclusive_group()
    modo.add_argument("--pendentes", action="store_true", help="eventos desde a última leitura (padrão)")
    modo.add_argument("--seguir", action="store_true", help="fica ouvindo e imprime cada evento novo")
    sub("historico", "o que aconteceu nos projetos num período", _historico).add_argument(
        "--desde", default="1d", help="1d, 7d, 12h ou data ISO (padrão 1d)")
    sub("clima", "clima de agora em São Paulo", _clima)
    p = sub("enviar", "envia uma mensagem a um agente e registra a ação", _enviar)
    alvo = p.add_mutually_exclusive_group(required=True)
    alvo.add_argument("--projeto", help="nome do projeto ou worktree no Orca")
    alvo.add_argument("--terminal", help="handle do terminal (term_...)")
    conteudo = p.add_mutually_exclusive_group(required=True)
    conteudo.add_argument("--texto", help="mensagem enviada com Enter")
    conteudo.add_argument("--tecla", help="tecla/opção enviada sem Enter (ex.: 1)")
    p.add_argument("--origem", required=True, choices=["voz", "texto", "regra"])
    p.add_argument("--motivo", default="", help="ordem do usuário ou regra aplicada")
    p = sub("lancar", "dá uma tarefa ao agente de um projeto (reaproveita ou abre)", _lancar)
    p.add_argument("--projeto", required=True)
    p.add_argument("--tarefa", required=True)
    p.add_argument("--origem", required=True, choices=["voz", "texto"])
    p = sub("regra", "regras do senhor: adicionar (pede confirmação) ou remover", _regra)
    p.add_argument("acao", choices=["adicionar", "remover"])
    p.add_argument("texto", nargs="+")
    sub("confirmar", "executa uma pendência aprovada pelo senhor", _decidir).add_argument("id", type=int)
    sub("recusar", "descarta uma pendência", _decidir).add_argument("id", type=int)
    sub("pendencias", "pendências aguardando o senhor", _pendencias)
    sub("vigia", "loop que registra mudanças das sessões", _vigia)
    sub("hook-fala", "hook Stop: fala a resposta do Jarvis", _hook_fala)
    sub("ouvir", "aperta-e-fala: começa ou termina a gravação", _ouvir)
    sub("calar", "interrompe a fala", _calar)
    sub("mudo", "liga ou desliga o modo mudo", _mudo).add_argument("estado", choices=["on", "off"])
    sub("instalar", "instala serviços, atalhos e o comando jarvis", _instalar)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = _parser().parse_args(argv or ["iniciar"])
    return args.handler(args)
