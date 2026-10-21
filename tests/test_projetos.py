import json
import os
import subprocess

import pytest

from jarvis import projetos
from jarvis.orca import Agente

AGORA = projetos._ts("2026-10-20T12:00:00Z")


def _jsonl(caminho, linhas, mtime=None):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("\n".join(json.dumps(l, ensure_ascii=False) for l in linhas) + "\n")
    if mtime:
        os.utime(caminho, (mtime, mtime))
    return caminho


def _claude(tipo, conteudo, ts="2026-10-19T15:20:07Z", **extra):
    return {"type": tipo, "timestamp": ts, "message": {"content": conteudo}, **extra}


@pytest.fixture
def casa(tmp_path, monkeypatch):
    monkeypatch.setattr(projetos, "_home", lambda: tmp_path)
    projetos._cache.clear()
    return tmp_path


def sem_commit(_caminho):
    return "", 0.0


def test_pasta_claude_troca_tudo_que_nao_e_letra_ou_numero(casa):
    assert projetos.pasta_claude("/git/app-analise_saude.v2") == casa / ".claude/projects/-git-app-analise-saude-v2"


def test_troca_claude_pega_ultimo_pedido_real_e_ultima_resposta_em_texto():
    linhas = [json.dumps(l) for l in [
        _claude("user", "merge pra master"),
        _claude("assistant", [{"type": "text", "text": "Vou mesclar."}, {"type": "tool_use", "name": "Bash"}]),
        _claude("user", [{"type": "tool_result", "content": "ok"}]),
        _claude("user", "<command-name>/model</command-name>"),
        _claude("user", [{"type": "text", "text": "Another Claude session sent a message: x"}]),
        _claude("user", "lembrete interno", isMeta=True),
        _claude("assistant", [{"type": "text", "text": "Mesclei na master."}], ts="2026-10-19T15:30:00Z"),
        _claude("assistant", [{"type": "thinking", "thinking": "..."}], ts="2026-10-19T15:31:00Z"),
        "linha quebrada {",
    ]]
    pedido, resposta, ts = projetos.troca_claude(linhas)
    assert pedido == "merge pra master"
    assert resposta == "Mesclei na master."
    assert ts == projetos._ts("2026-10-19T15:30:00Z")


def test_troca_codex_le_mensagens_do_rollout():
    linhas = [json.dumps(l) for l in [
        {"type": "session_meta", "payload": {"cwd": "/git/x"}},
        {"type": "response_item", "timestamp": "2026-10-20T10:00:00Z",
         "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "corrige o login"}]}},
        {"type": "response_item", "timestamp": "2026-10-20T10:05:00Z",
         "payload": {"type": "message", "role": "assistant",
                     "content": [{"type": "output_text", "text": "Login corrigido."}]}},
    ]]
    assert projetos.troca_codex(linhas) == ("corrige o login", "Login corrigido.", projetos._ts("2026-10-20T10:05:00Z"))


def test_sessoes_codex_agrupa_por_pasta_e_ignora_o_jarvis_reserva(casa):
    base = casa / ".codex/sessions/2026/10/20"
    meta = lambda cwd: {"type": "session_meta", "payload": {"cwd": cwd}}  # noqa: E731
    _jsonl(base / "rollout-a.jsonl", [meta("/git/x")], mtime=AGORA - 100)
    novo = _jsonl(base / "rollout-b.jsonl", [meta("/git/x")], mtime=AGORA - 10)
    _jsonl(base / "rollout-c.jsonl", [meta(str(projetos.RAIZ / "sessao"))], mtime=AGORA - 5)
    _jsonl(base / "rollout-d.jsonl", [meta("/git/velho")], mtime=AGORA - 90 * 86400)
    assert projetos.sessoes_codex(agora=AGORA) == {"/git/x": (novo, AGORA - 10)}


def test_montar_usa_o_historico_mais_recente_e_ordena_por_atividade(casa):
    _jsonl(projetos.pasta_claude("/git/saude") / "s1.jsonl", [
        _claude("user", "merge pra master"),
        _claude("assistant", [{"type": "text", "text": "Plano 4 mesclado."}], ts="2026-10-19T15:20:00Z"),
    ], mtime=AGORA - 3600)
    codex_x = _jsonl(casa / "rollout.jsonl", [
        {"type": "response_item", "timestamp": "2026-10-20T10:05:00Z",
         "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Feito."}]}},
    ], mtime=AGORA)
    repos = [{"path": "/git/saude", "displayName": "app-analise-saude"}, {"path": "/git/x", "displayName": "x"},
             {"path": "/git/parado", "displayName": "parado"}, {"path": "/", "displayName": "/"}]
    commits = {"/git/parado": ("init", AGORA - 86400 * 40)}
    lista = projetos.montar(repos, [], codex={"/git/x": (codex_x, AGORA)},
                            commit=lambda c: commits.get(c, ("", 0.0)))
    assert [p.nome for p in lista] == ["x", "app-analise-saude", "parado"]  # "/" fica de fora
    x, saude, parado = lista
    assert (x.agente, x.resposta) == ("codex", "Feito.")
    assert (saude.agente, saude.pedido, saude.resposta) == ("claude", "merge pra master", "Plano 4 mesclado.")
    assert parado.agente == "" and parado.commit == "init"


def test_montar_le_tambem_os_worktrees_do_projeto(casa):
    _jsonl(projetos.pasta_claude("/home/u/orca/workspaces/postos/ajustes") / "s.jsonl", [
        _claude("assistant", [{"type": "text", "text": "Ajustes prontos."}]),
    ])
    repos = [{"path": "/git/postos", "displayName": "gestao-postos"}]
    worktrees = [{"repo": "gestao-postos", "path": "/home/u/orca/workspaces/postos/ajustes"}]
    [p] = projetos.montar(repos, worktrees, codex={}, commit=sem_commit)
    assert p.resposta == "Ajustes prontos."


def test_aba_aberta_no_orca_vale_quando_e_mais_nova(casa):
    repos = [{"path": "/opt", "displayName": "hostinger-sv"}]
    agente = Agente(pane_key="t:1", projeto="hostinger-sv", worktree="opt", caminho="/opt", agente="claude",
                    estado="done", ultima_mensagem="Escalabilidade: faz sentido.", prompt="isso escala?",
                    estado_desde_ms=int((AGORA - 600) * 1000), ferramenta=None)
    [p] = projetos.montar(repos, [], codex={}, commit=sem_commit, agentes=[agente])
    assert (p.sessao, p.agente, p.resposta, p.pedido) == ("done", "claude", "Escalabilidade: faz sentido.", "isso escala?")
    assert p.ts == AGORA - 600
    assert "aba aberta: concluiu" in projetos.formatar_lista([p], AGORA)


def test_formatar_lista_resume_e_lista_o_resto_pelo_nome():
    ps = [projetos.Projeto(nome=f"p{i}", caminho=f"/git/p{i}", ts=AGORA - i * 86400) for i in range(12)]
    ps[0].agente, ps[0].resposta, ps[0].ts_agente = "claude", "Tudo  pronto\nno deploy.", AGORA - 120
    texto = projetos.formatar_lista(ps, AGORA, limite=10)
    assert texto.splitlines()[0] == "• p0 — há 0 min — último agente (claude, há 2 min): «Tudo pronto no deploy.»"
    assert texto.splitlines()[-1] == "(+2 projetos sem atividade recente: p10, p11)"


def test_encontrar_por_nome_parcial_e_ambiguo():
    ps = [projetos.Projeto(nome="app-analise-saude", caminho="/git/app-analise-saude"),
          projetos.Projeto(nome="dailytracker-app", caminho="/git/dailytracker/dailytracker-app"),
          projetos.Projeto(nome="dailytracker-service", caminho="/git/dailytracker/dailytracker-service")]
    assert projetos.encontrar("saude", ps).nome == "app-analise-saude"
    with pytest.raises(ValueError, match="Mais de um"):
        projetos.encontrar("dailytracker", ps)
    with pytest.raises(ValueError, match="Não achei"):
        projetos.encontrar("xyz", ps)


def test_ultimo_commit_com_git_de_verdade(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                    "--allow-empty", "-m", "primeiro"], check=True)
    assunto, ts = projetos.ultimo_commit(str(tmp_path))
    assert assunto == "primeiro" and ts > 0
    assert projetos.ultimo_commit(str(tmp_path / "nao-existe")) == ("", 0.0)
