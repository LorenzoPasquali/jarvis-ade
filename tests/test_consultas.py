from datetime import datetime, timedelta, timezone

import pytest

from conftest import ag, carregar
from jarvis.consultas import commits, descrever_clima, formatar_historico, formatar_status, parse_periodo
from jarvis.orca import Terminal

AGORA_MS = 1792422000000 + 5 * 60_000


def test_status_exclui_jarvis_e_traduz_estado():
    s = formatar_status([ag("J", "working"), ag("S", "waiting", projeto="app-analise-saude", mensagem="Posso seguir?")],
                        {"S": Terminal("term_s", "S", "/git/app-analise-saude", True)}, "J", agora_ms=AGORA_MS)
    assert "app-analise-saude" in s and "aguardando resposta" in s and "term_s" in s
    assert "há 5 min" in s and "«Posso seguir?»" in s
    assert s.count("•") == 1


def test_status_sem_terminal():
    s = formatar_status([ag("S", "done")], {}, None, agora_ms=AGORA_MS)
    assert "concluiu" in s and "sem terminal" in s


def test_status_vazio():
    assert formatar_status([], {}, None, 0) == "Nenhuma outra sessão de agente aberta no Orca."


def test_parse_periodo():
    agora = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)
    assert parse_periodo("7d", agora) == agora - timedelta(days=7)
    assert parse_periodo("3h", agora) == agora - timedelta(hours=3)
    assert parse_periodo("2026-10-18T00:00:00+00:00", agora) == datetime(2026, 10, 18, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        parse_periodo("ontem", agora)


def test_commits_pasta_nao_git(tmp_path):
    assert commits(str(tmp_path), datetime.now(timezone.utc)) == []


def test_commits_repo_real(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "a").write_text("x")
    subprocess.run(["git", "-C", str(tmp_path), "add", "a"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-q", "-m", "primeiro commit"], check=True)
    linhas = commits(str(tmp_path), datetime.now(timezone.utc) - timedelta(days=1))
    assert len(linhas) == 1 and "primeiro commit" in linhas[0]


def test_formatar_historico_omite_projetos_vazios():
    evs = [{"tipo": "terminou", "projeto": "app-analise-saude"}, {"tipo": "terminou", "projeto": "app-analise-saude"},
           {"tipo": "aguardando", "projeto": "app-analise-saude"}]
    texto = formatar_historico(evs, {"app-analise-saude": ["abc123 2026-10-19 plano 4"], "dailytracker": []},
                               datetime(2026, 10, 12, tzinfo=timezone.utc))
    assert "app-analise-saude" in texto and "terminou: 2" in texto and "plano 4" in texto
    assert "dailytracker" not in texto


def test_descrever_clima():
    t = descrever_clima(carregar("open_meteo.json"))
    assert t.startswith("São Paulo agora: 21 °C (sensação 23 °C), parcialmente nublado.")
    assert "mínima 14 °C, máxima 23 °C, chance de chuva 12%" in t


def test_clima_curto():
    from jarvis.consultas import clima_curto
    assert clima_curto(carregar("open_meteo.json")) == "21 °C, parcialmente nublado em São Paulo"
