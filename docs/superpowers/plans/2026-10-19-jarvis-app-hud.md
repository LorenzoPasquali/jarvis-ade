# Jarvis App com HUD — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jarvis sempre ligado: um cérebro (Claude Code headless) roda desde o login e Super+J abre uma janela translúcida de tela inteira para conversar por voz e texto, ver as sessões e confirmar ações.

**Architecture:** `jarvis-cerebro` (Python stdlib, systemd user) mantém um `claude -p` em stream-json, recebe falas/textos da janela e eventos do vigia, transmite a resposta à janela por SSE e manda as linhas `🔊` ao servidor de voz. `jarvis-hud` é uma janela GTK3 + WebKit2 4.1 transparente que carrega a interface HTML/CSS/JS servida pelo cérebro. Ações sensíveis viram pendências que só executam com aprovação na janela ou "sim" falado.

**Tech Stack:** Python 3.12 stdlib + pytest; PyGObject (Gtk 3.0, WebKit2 4.1); HTML/CSS/JS sem framework, fontes locais; Claude Code 2.1.303 CLI headless; Orca 1.4.230; serviços existentes `jarvis-voz` e `jarvis-vigia`.

**Spec:** `docs/superpowers/specs/2026-10-19-jarvis-app-hud-design.md` (evolui `docs/superpowers/specs/2026-10-19-jarvis-orquestrador-design.md`)

## Global Constraints

- Português do Brasil em toda interface e fala; o Jarvis trata o usuário por "senhor".
- Orca sempre por caminho absoluto (`jarvis.orca.orca_cli()`); `/usr/bin/orca` é o leitor de tela do GNOME.
- Sem chave de API: o cérebro roda o CLI `claude` do usuário (`-p --input-format stream-json --output-format stream-json --include-partial-messages --verbose`), modelo padrão `sonnet`, configurável por `JARVIS_MODELO`.
- Janela de **tela inteira**, véu translúcido sobre a área de trabalho (1680x1050), Esc ou clique fora do conteúdo fecha.
- Super+J = "falar com o Jarvis": fechada → abre e ouve; ouvindo → encerra e envia; aberta parada → ouve de novo.
- Fim da escuta: silêncio de ~1 s depois de fala, ou novo Super+J; enquanto ouve, o Jarvis não fala.
- Tela bloqueada: sem fala e sem turnos do Claude; eventos na fila; resumo único ao desbloquear.
- Só `terminou`, `aguardando`, `permissao`, `travou`, `orca_indisponivel` viram turno do Claude.
- Ordem falada para agente, nova regra e abrir agente por voz só executam após aprovação (botão na janela ou "sim").
- "Roda o agente": sessão parada do projeto recebe a tarefa; sessão trabalhando → perguntar; sem sessão → `orca agent launch --agent claude --worktree path:<pasta> --prompt <tarefa>`; nunca criar worktree/branch.
- Servidores locais recusam pedidos com `Origin` diferente do próprio app e exigem `application/json` em POST.
- Interface respeita `prefers-reduced-motion`; fontes empacotadas em `hud/fontes/` (licença OFL), sem CDN em tempo de uso.
- Aba Jarvis do Orca aposentada: sem `Monitor`, sem hook Stop de fala; `jarvis` sem argumentos abre a janela.
- Nada do app antigo do Codex é apagado sem confirmação do usuário.
- Commits terminam com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Claude headless morre ou trava** (CLI atualizado, rede fora, limite de uso): o cérebro reinicia com `--resume`, a janela mostra o estado e nada fica "pensando" para sempre. → teste na Task 2.
2. **Janela aberta sem cérebro rodando** (serviço reiniciando): a interface mostra "Jarvis desconectado" e reconecta sozinha, sem tela vazia. → teste/verificação na Task 7.
3. **Fala do usuário enquanto o Jarvis ainda responde** (nova pergunta no meio de um turno): a fala em curso para, a mensagem nova entra na fila e é respondida depois, sem misturar respostas. → teste na Task 6.
4. **Pendência esquecida** (cartão nunca respondido, ou "sim" que chega depois de expirar): expira em 10 min sem executar e o Jarvis avisa. → teste na Task 4.
5. **Evento que chega durante um turno do usuário**: espera o turno terminar e entra agrupado no próximo, sem cortar a resposta. → teste na Task 6.

---

## Estrutura de arquivos

```
hud/index.html  hud/estilo.css  hud/app.js  hud/fontes/   # interface (servida pelo cérebro)
hud/janela.py                     # janela GTK transparente + aviso discreto (python3 do sistema)
jarvis/cerebro/__init__.py
jarvis/cerebro/claude.py          # ProcessoClaude: stream-json
jarvis/cerebro/fala.py            # SeparadorFala: deltas -> linhas 🔊 -> voz
jarvis/cerebro/escuta.py          # Escuta: pw-record + níveis + silêncio; tela_bloqueada()
jarvis/cerebro/eventos.py         # FilaEventos: cursor próprio, filtro, bloqueio
jarvis/cerebro/servidor.py        # HTTP + SSE para a janela
jarvis/cerebro/main.py            # Cerebro: liga tudo; `jarvis cerebro`
jarvis/pendencias.py              # pendências e confirmação (CLI e cérebro)
jarvis/lancar.py                  # `jarvis lancar`
jarvis/permissao_mcp.py           # `jarvis permissao-mcp` (servidor MCP stdio)
sessao/cerebro-settings.json      # permissões do cérebro (sem hook de fala)
systemd/jarvis-cerebro.service    autostart/jarvis-hud.desktop
```

---

### Task 1: Visual da janela, janela GTK e `jarvis hud --demo`

**Files:**
- Create: `hud/index.html`, `hud/estilo.css`, `hud/app.js`, `hud/fontes/*`, `hud/janela.py`, `jarvis/hud_cli.py`, `tests/test_hud.py`
- Modify: `jarvis/cli.py` (subcomando `hud`)

**Interfaces:**
- Produces:
  - `hud/index.html` com regiões de id fixo: `#nucleo` (núcleo animado), `#estado` (texto do estado), `#sessoes` (lista), `#conversa` (mensagens), `#cartoes` (confirmações), `#entrada` (form com `<input id="texto">`), `#sistema` (relógio, clima curto, voz/Orca). Clique em `#veu` (fundo) fecha.
  - `body[data-estado]` ∈ `ocioso|ouvindo|pensando|falando|desconectado` controla o visual do núcleo; `--nivel` (0..1, CSS custom property em `#nucleo`) anima com o microfone.
  - `app.js` expõe `window.jarvis = {abrir(), fechar(), aplicar(evento)}`. `aplicar` aceita os eventos SSE da Task 6 (`estado`, `nivel`, `usuario`, `delta`, `resposta_fim`, `sessoes`, `cartao`, `cartao_fim`, `sistema`, `historico`). `?demo=1` gera dados de exemplo realistas e percorre os estados sem servidor.
  - `fechar()` chama `window.webkit.messageHandlers.jarvis.postMessage("fechar")` quando existir.
  - `hud/janela.py`: `python3 hud/janela.py [--url URL] [--mostrar]` — `Gtk.Window` sem borda, `fullscreen()`, visual RGBA (`screen.get_rgba_visual()`), `set_app_paintable(True)`, `WebKit2.WebView` com `set_background_color(Gdk.RGBA(0,0,0,0))`, `set_keep_above(True)`, `set_skip_taskbar_hint(True)`; começa escondida (salvo `--mostrar`); grava pid em `dados/hud.pid`; `SIGUSR1` → mostrar, `present()`, rodar `jarvis.abrir()`; mensagem `"fechar"` → esconder. URL padrão `http://127.0.0.1:8766/`.
  - `jarvis hud [--demo]`: se `dados/hud.pid` aponta para um `hud/janela.py` vivo → `SIGUSR1` e `POST /api/super-j` no cérebro (ignora falha); senão inicia `hud/janela.py --mostrar` (com `--url file://.../hud/index.html?demo=1` se `--demo`).
- [ ] **Step 1: Plano de design (skill `frontend-design`)** — escrever no ledger: paleta (4–6 hex nomeados), fontes (baixar woff2 OFL para `hud/fontes/`), conceito de layout em ASCII para tela inteira 1680x1050, princípios; revisar contra os traços genéricos listados na skill e registrar o que mudou.
- [ ] **Step 2: Testes que falham** (`tests/test_hud.py`)

```python
def test_index_tem_regioes():
    html = (RAIZ / "hud/index.html").read_text()
    for regiao in ["nucleo", "estado", "sessoes", "conversa", "cartoes", "entrada", "sistema", "veu"]:
        assert f'id="{regiao}"' in html
    assert 'lang="pt-BR"' in html

def test_fontes_locais_sem_cdn():
    css = (RAIZ / "hud/estilo.css").read_text()
    assert "@font-face" in css and "fonts.googleapis" not in css and "http" not in css.split("@font-face")[1][:400]
    assert "prefers-reduced-motion" in css

def test_app_trata_todos_os_eventos():
    js = (RAIZ / "hud/app.js").read_text()
    for tipo in ["estado", "nivel", "usuario", "delta", "resposta_fim", "sessoes", "cartao", "cartao_fim", "sistema", "historico"]:
        assert f'"{tipo}"' in js or f"'{tipo}'" in js

def test_hud_alterna_janela_viva(dados_tmp, monkeypatch):
    sinais = []
    monkeypatch.setattr(hud_cli, "_janela_viva", lambda pid: True)
    monkeypatch.setattr(hud_cli.os, "kill", lambda pid, sig: sinais.append(sig))
    monkeypatch.setattr(hud_cli, "_avisar_cerebro", lambda: None)
    (dados_tmp / "hud.pid").write_text("4242")
    assert hud_cli.hud(demo=False) == 0 and sinais == [signal.SIGUSR1]
```

(`hud_cli` = `jarvis/hud_cli.py`, com `hud(demo: bool) -> int`, `_janela_viva(pid) -> bool` checando `/proc/<pid>/cmdline` contém `hud/janela.py`, `_avisar_cerebro() -> None`.)
- [ ] **Step 3: `python3 -m pytest tests/test_hud.py -q`** → FAIL
- [ ] **Step 4: Implementar** a interface seguindo o plano de design, `hud/janela.py`, `jarvis/hud_cli.py` e o subcomando.
- [ ] **Step 5: Testes** → PASS. Crítica visual: `google-chrome --headless --screenshot=<scratchpad>/hud.png --window-size=1680,1050 "file:///git/jarvis/hud/index.html?demo=1&fundo=1"` (`fundo=1` põe uma imagem de área de trabalho atrás, só para a captura) e ler a imagem; corrigir o que destoa do plano. Abrir de verdade: `bin/jarvis hud --demo` mostra a janela transparente por cima da tela; Esc fecha.
- [ ] **Step 6: Commit** `feat: visual da janela do Jarvis e janela GTK transparente`

---

### Task 2: Processo Claude headless e separação da fala

**Files:**
- Create: `jarvis/cerebro/__init__.py`, `jarvis/cerebro/claude.py`, `jarvis/cerebro/fala.py`, `tests/fixtures/claude_falso.py`, `tests/test_cerebro_claude.py`, `tests/test_cerebro_fala.py`

**Interfaces:**
- Consumes: `jarvis.texto_fala.extrair_fala`, `MARCADOR`, `SILENCIO`.
- Produces:
  - `class ProcessoClaude(comando: list[str], cwd: Path, env: dict, ao_evento: Callable[[dict], None], arquivo_sessao: Path)`:
    - `iniciar()` — sobe o processo; se `arquivo_sessao` tem `session_id`, acrescenta `--resume <id>`.
    - `enviar(texto: str) -> None` — escreve `{"type":"user","message":{"role":"user","content":texto}}\n` no stdin; marca `ocupado = True`.
    - Thread leitora: cada linha JSON vira `ao_evento(dict)`; `system/init` e `result` gravam o `session_id`; `result` marca `ocupado = False`.
    - Se o processo sair: `ao_evento({"type": "jarvis_reiniciando"})`, espera 2 s, reinicia com `--resume`; se estava ocupado, emite `{"type": "result", "subtype": "error_restart", "is_error": True}` para ninguém ficar esperando.
    - `parar()`.
  - `comando_claude(raiz: Path, modelo: str) -> list[str]` — `["claude","-p","--input-format","stream-json","--output-format","stream-json","--include-partial-messages","--verbose","--model",modelo,"--settings",str(raiz/"sessao/cerebro-settings.json"),"--mcp-config",<json com servidor "jarvis": command str(raiz/"bin/jarvis"), args ["permissao-mcp"]>,"--permission-prompt-tool","mcp__jarvis__permissao"]`.
  - `class SeparadorFala(falar: Callable[[str], None])`: `alimentar(delta: str)` — a cada linha completa iniciada por `🔊` chama `falar(extrair_fala(linha))`; `fim(texto_completo: str)` — processa a última linha parcial; se a mensagem não teve linha `🔊` nem `🔇`, fala `extrair_fala(texto_completo)`; `reiniciar()`.
- `tests/fixtures/claude_falso.py`: lê linhas do stdin; para cada mensagem emite `system/init` (com `session_id` `"sess-teste"`, uma vez), `stream_event`s `content_block_delta` com o texto `"Olá, senhor.\n🔊 Tudo certo.\n"` em 3 pedaços, `assistant`, `result` (com `session_id`). Se a mensagem contiver `"MORRA"`, sai com código 1 sem `result`.

- [ ] **Step 1: Testes que falham**

```python
def test_resposta_completa_e_sessao_gravada(tmp_path):
    eventos = []
    p = ProcessoClaude([sys.executable, FALSO], tmp_path, os.environ.copy(), eventos.append, tmp_path / "s.json")
    p.iniciar(); p.enviar("oi")
    esperar(lambda: any(e["type"] == "result" for e in eventos))
    assert not p.ocupado and json.loads((tmp_path / "s.json").read_text())["session_id"] == "sess-teste"
    deltas = "".join(e["event"]["delta"]["text"] for e in eventos
                     if e["type"] == "stream_event" and e["event"]["type"] == "content_block_delta")
    assert deltas == "Olá, senhor.\n🔊 Tudo certo.\n"
    p.parar()

def test_retoma_sessao_ao_reiniciar(tmp_path):
    (tmp_path / "s.json").write_text('{"session_id": "abc"}')
    p = ProcessoClaude([sys.executable, FALSO], tmp_path, os.environ.copy(), lambda e: None, tmp_path / "s.json")
    assert p.comando_atual()[-2:] == ["--resume", "abc"]

def test_morte_no_meio_libera_e_reinicia(tmp_path):
    eventos = []
    p = ProcessoClaude([sys.executable, FALSO], tmp_path, os.environ.copy(), eventos.append, tmp_path / "s.json")
    p.iniciar(); p.enviar("MORRA")
    esperar(lambda: any(e.get("subtype") == "error_restart" for e in eventos), limite=6)
    assert not p.ocupado and any(e["type"] == "jarvis_reiniciando" for e in eventos)
    p.enviar("oi")
    esperar(lambda: sum(e["type"] == "result" for e in eventos) >= 2, limite=6)
    p.parar()

def test_comando_claude_tem_flags():
    c = comando_claude(RAIZ, "sonnet")
    for f in ["--input-format", "stream-json", "--include-partial-messages", "--permission-prompt-tool",
              "mcp__jarvis__permissao", "--settings"]:
        assert f in c

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
    s = SeparadorFala(falas.append); s.alimentar("O app terminou. Tudo certo.")
    s.fim("O app terminou. Tudo certo.")
    assert falas == ["O app terminou. Tudo certo."]

def test_separador_silencio():
    falas = []
    s = SeparadorFala(falas.append); s.alimentar("Monitor ok.\n🔇"); s.fim("Monitor ok.\n🔇")
    assert falas == []
```

- [ ] **Step 2: Rodar** → FAIL
- [ ] **Step 3: Implementar**
- [ ] **Step 4: Rodar** → PASS
- [ ] **Step 5: Commit** `feat: processo Claude headless e separação da fala`

---

### Task 3: Escuta (microfone, nível, silêncio) e tela bloqueada

**Files:**
- Create: `jarvis/cerebro/escuta.py`, `tests/test_cerebro_escuta.py`

**Interfaces:**
- Consumes: `jarvis.voz_cliente.transcricao_util`, `chamar`.
- Produces:
  - `rms(pcm: bytes) -> float` — PCM s16le mono, resultado 0..1.
  - `class DetectorSilencio(limiar: float = 0.02, silencio_s: float = 1.0, espera_fala_s: float = 6.0, maximo_s: float = 30.0)`: `alimentar(nivel: float, t: float) -> str | None` devolve `None` (continua), `"fim"` (houve fala e depois `silencio_s` abaixo do limiar, ou passou `maximo_s`) ou `"vazio"` (nenhuma fala em `espera_fala_s`).
  - `class Escuta(ao_nivel: Callable[[float], None], ao_fim: Callable[[str | None], None], chamar=voz_cliente.chamar)`: `iniciar()` — `chamar("/parar")`, `chamar("/ouvindo", {"ligado": True})`, `pw-record --rate 16000 --channels 1 --format s16 dados/escuta.wav`, thread que lê o arquivo crescendo a cada 100 ms, manda `ao_nivel(rms)` e alimenta o detector; `encerrar()` — termina e transcreve; ao fim chama `chamar("/ouvindo", {"ligado": False})` e `ao_fim(texto_util ou None)`; `ativa: bool`.
  - `tela_bloqueada(runner=subprocess.run) -> bool` — `gdbus call --session --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver --method org.gnome.ScreenSaver.GetActive`; `"(true,)"` → True; erro → False.

- [ ] **Step 1: Testes que falham**

```python
def test_rms():
    assert rms(b"\x00\x00" * 160) == 0.0
    assert rms(struct.pack("<160h", *([16384] * 160))) == pytest.approx(0.5, abs=0.01)

def test_detector_fim_depois_de_fala_e_silencio():
    d = DetectorSilencio()
    assert d.alimentar(0.2, 0.0) is None and d.alimentar(0.2, 0.5) is None
    assert d.alimentar(0.0, 1.0) is None and d.alimentar(0.0, 2.1) == "fim"

def test_detector_vazio_sem_fala():
    d = DetectorSilencio()
    assert d.alimentar(0.0, 3.0) is None and d.alimentar(0.0, 6.1) == "vazio"

def test_detector_maximo():
    d = DetectorSilencio()
    d.alimentar(0.3, 0.0)
    assert d.alimentar(0.3, 30.1) == "fim"

def test_tela_bloqueada():
    r = lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout="(true,)\n", stderr="")
    assert tela_bloqueada(runner=r) is True
    r2 = lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout="(false,)\n", stderr="")
    assert tela_bloqueada(runner=r2) is False
    def falha(*a, **k): raise FileNotFoundError()
    assert tela_bloqueada(runner=falha) is False
```

- [ ] **Step 2: Rodar** → FAIL
- [ ] **Step 3: Implementar**
- [ ] **Step 4: Rodar** → PASS. Real: script curto que inicia `Escuta` com `print` nos callbacks, falar "teste" e calar → níveis sobem, `ao_fim("teste…")` ~1 s depois do silêncio.
- [ ] **Step 5: Commit** `feat: escuta com nível do microfone, fim por silêncio e detecção de tela bloqueada`

---

### Task 4: Pendências, `jarvis lancar`, `jarvis regra`, confirmar/recusar

**Files:**
- Create: `jarvis/pendencias.py`, `jarvis/lancar.py`, `tests/test_pendencias.py`, `tests/test_lancar.py`
- Modify: `jarvis/enviar.py` (origem `voz` vira pendência), `jarvis/cli.py` (`lancar`, `regra`, `confirmar`, `recusar`, `pendencias`)

**Interfaces:**
- Consumes: `enviar.resolver_destino`, `enviar.enviar`, `orca.agentes`, `orca.terminais`, `orca.executar`, `sessao.ler`.
- Produces:
  - Pendência = `{"id": int, "criada_em": iso, "tipo": "enviar"|"regra"|"lancar", "descricao": str, "dados": dict, "estado": "aguardando"|"executada"|"recusada"|"expirada"|"falhou", "resultado": str}` em `dados/pendencias.json`.
  - `pendencias.criar(tipo: str, descricao: str, dados: dict) -> dict`; `listar(apenas_abertas: bool = True) -> list[dict]` (expira as com mais de `EXPIRA_S = 600`); `confirmar(id: int) -> dict` (executa: `enviar` → `enviar.enviar(..., origem="voz", confirmado=True)`; `regra` → acrescenta `- <texto>` em `sessao/regras.md` sob "## Regras ativas", removendo "(nenhuma)"; `lancar` → `lancar.executar_lancamento(dados)`); `recusar(id: int) -> dict`. Confirmar pendência não aberta → `ValueError`.
  - `enviar` CLI com `--origem voz`: não envia; cria pendência `enviar` com destino e texto e imprime `Aguardando confirmação do senhor (pendência <id>): enviar a <projeto>: «<texto>»`. Flag `--confirmado` deixa de existir.
  - `lancar.planejar(projeto: str, tarefa: str, agentes, repos) -> dict` — `{"acao": "enviar", "destino": Destino}` se há sessão parada (`done`/`waiting`/`idle`) do projeto; `{"acao": "perguntar", "motivo": ...}` se só há sessão `working`/`permission`; `{"acao": "abrir", "caminho": <path do repo>}` se não há sessão; projeto inexistente ou ambíguo → `ValueError` com opções. `executar_lancamento(dados) -> str` — `orca agent launch --agent claude --worktree path:<caminho> --prompt <tarefa>` (registra em `dados/acoes.jsonl` com `origem`).
  - CLI: `jarvis lancar --projeto P --tarefa T --origem {voz,texto}` (voz → pendência; texto → executa o plano; `perguntar` → imprime o motivo e retorna 1); `jarvis regra adicionar "<texto>"` (sempre pendência); `jarvis regra remover <n>` (remove direto); `jarvis confirmar <id>`, `jarvis recusar <id>`, `jarvis pendencias`.

- [ ] **Step 1: Testes que falham**

```python
def test_criar_e_confirmar_regra(dados_tmp, regras_tmp):
    p = pendencias.criar("regra", "Nova regra", {"texto": "app-analise-saude: pode aprovar testes"})
    assert pendencias.listar()[0]["id"] == p["id"]
    pendencias.confirmar(p["id"])
    texto = regras_tmp.read_text()
    assert "- app-analise-saude: pode aprovar testes" in texto and "(nenhuma)" not in texto
    assert pendencias.listar() == []

def test_recusar_nao_executa(dados_tmp, regras_tmp):
    p = pendencias.criar("regra", "x", {"texto": "y"})
    pendencias.recusar(p["id"])
    assert "- y" not in regras_tmp.read_text()

def test_pendencia_expira(dados_tmp, monkeypatch):
    p = pendencias.criar("regra", "x", {"texto": "y"})
    monkeypatch.setattr(pendencias.time, "time", lambda: time.time() + 601)
    assert pendencias.listar() == []
    with pytest.raises(ValueError):
        pendencias.confirmar(p["id"])

def test_confirmar_duas_vezes_falha(dados_tmp, regras_tmp):
    p = pendencias.criar("regra", "x", {"texto": "y"})
    pendencias.confirmar(p["id"])
    with pytest.raises(ValueError):
        pendencias.confirmar(p["id"])

def test_planejar_reaproveita_sessao_parada():
    plano = lancar.planejar("dailytracker", "rodar testes", [ag("D", "done", projeto="dailytracker")], REPOS)
    assert plano["acao"] == "enviar"

def test_planejar_pergunta_se_trabalhando():
    assert lancar.planejar("dailytracker", "x", [ag("D", "working", projeto="dailytracker")], REPOS)["acao"] == "perguntar"

def test_planejar_abre_sem_sessao():
    plano = lancar.planejar("dailytracker", "x", [], REPOS)
    assert plano == {"acao": "abrir", "caminho": "/git/dailytracker", "tarefa": "x"}

def test_lancamento_usa_orca_agent_launch(dados_tmp):
    chamadas = []
    lancar.executar_lancamento({"caminho": "/git/dailytracker", "tarefa": "rodar testes", "origem": "texto"},
                               executar=lambda a, **k: chamadas.append(a) or {})
    assert chamadas[0] == ["agent", "launch", "--agent", "claude", "--worktree", "path:/git/dailytracker",
                           "--prompt", "rodar testes"]

def test_enviar_por_voz_vira_pendencia(dados_tmp, capsys, monkeypatch):
    ... # monkeypatch orca.agentes/terminais/sessao; cli.main(["enviar","--projeto","app-analise-saude","--texto","segue","--origem","voz"])
    assert "Aguardando confirmação" in capsys.readouterr().out and pendencias.listar()[0]["tipo"] == "enviar"
```

(`REPOS = [{"displayName": "dailytracker", "path": "/git/dailytracker"}]`; fixture `regras_tmp` aponta `pendencias.ARQUIVO_REGRAS` para uma cópia de `sessao/regras.md` em `tmp_path`.)
- [ ] **Step 2: Rodar** → FAIL
- [ ] **Step 3: Implementar**; remover `--confirmado` do CLI e ajustar `tests/test_enviar.py` (voz confirmada passa a ser só via `pendencias.confirmar`).
- [ ] **Step 4: Rodar a suíte inteira** → PASS
- [ ] **Step 5: Commit** `feat: pendências com confirmação, jarvis lancar e jarvis regra`

---

### Task 5: Permissão do Claude pela janela (`jarvis permissao-mcp`)

**Files:**
- Create: `jarvis/permissao_mcp.py`, `tests/test_permissao_mcp.py`
- Modify: `jarvis/cli.py` (`permissao-mcp`)

**Interfaces:**
- Produces:
  - Servidor MCP stdio (JSON-RPC 2.0 por linha): `initialize` → `{"protocolVersion": <o do pedido>, "capabilities": {"tools": {}}, "serverInfo": {"name": "jarvis", "version": "1"}}`; `tools/list` → uma ferramenta `permissao` com `inputSchema` `{"type":"object","properties":{"tool_name":{"type":"string"},"input":{"type":"object"}},"required":["tool_name","input"]}`; `tools/call` → pergunta ao cérebro e devolve `{"content":[{"type":"text","text": json.dumps(decisao)}]}`, com `decisao` = `{"behavior":"allow","updatedInput": input}` ou `{"behavior":"deny","message": "..."}`; notificações (sem `id`) não têm resposta.
  - `decidir(tool_name: str, entrada: dict, perguntar=_perguntar_cerebro) -> dict` — `_perguntar_cerebro` faz `POST http://127.0.0.1:8766/api/permissao {"ferramenta","entrada"}` com timeout 130 s e devolve `{"aprovado": bool}`; erro/timeout → nega com `"O senhor não respondeu; não fiz isso."`.
  - Conferir na documentação do Claude Code 2.1.303 o formato exato esperado do `--permission-prompt-tool` e ajustar se divergir.

- [ ] **Step 1: Testes que falham** — rodar `jarvis permissao-mcp` como subprocesso e conversar por stdin/stdout:

```python
def test_initialize_e_lista():
    r = conversa([{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}},
                  {"jsonrpc":"2.0","method":"notifications/initialized"},
                  {"jsonrpc":"2.0","id":2,"method":"tools/list"}])
    assert r[0]["result"]["serverInfo"]["name"] == "jarvis" and r[1]["result"]["tools"][0]["name"] == "permissao"

def test_decidir_aprovado_e_negado():
    assert decidir("Bash", {"command": "ls"}, perguntar=lambda f, e: {"aprovado": True}) == \
        {"behavior": "allow", "updatedInput": {"command": "ls"}}
    assert decidir("Bash", {}, perguntar=lambda f, e: {"aprovado": False})["behavior"] == "deny"

def test_decidir_sem_cerebro_nega():
    def falha(f, e): raise OSError()
    assert decidir("Bash", {}, perguntar=falha)["behavior"] == "deny"
```

- [ ] **Step 2: Rodar** → FAIL
- [ ] **Step 3: Implementar**
- [ ] **Step 4: Rodar** → PASS
- [ ] **Step 5: Commit** `feat: pedidos de permissão do Claude viram cartão na janela`

---

### Task 6: Cérebro — servidor, fila de eventos, sessões e orquestração

**Files:**
- Create: `jarvis/cerebro/eventos.py`, `jarvis/cerebro/servidor.py`, `jarvis/cerebro/main.py`, `sessao/cerebro-settings.json`, `tests/test_cerebro_eventos.py`, `tests/test_cerebro_servidor.py`, `tests/test_cerebro_main.py`
- Modify: `sessao/CLAUDE.md`, `jarvis/cli.py` (`cerebro`)

**Interfaces:**
- Consumes: Tasks 2–5; `eventos.ler_desde`, `eventos.formatar`, `consultas.ESTADOS`, `dados/vigia-estado.json`.
- Produces:
  - `FilaEventos(cursor: Path)`: `coletar() -> list[dict]` lê novos eventos desde o cursor próprio `dados/cerebro-cursor` e guarda os dos tipos `terminou|aguardando|permissao|travou|orca_indisponivel`; `retirar() -> list[str]` devolve as linhas formatadas e esvazia; `vazia: bool`.
  - `servidor.criar(cerebro, porta: int = 8766) -> ThreadingHTTPServer`: `GET /` e `/<arquivo>` servem `hud/`; `GET /api/eventos` = SSE (`data: <json>\n\n`; ao conectar envia `historico` e `sessoes` atuais); `POST /api/mensagem {"texto"}`; `POST /api/super-j`; `POST /api/cartao {"id", "decisao": "aprovar"|"recusar"}`; `POST /api/permissao {"ferramenta","entrada"}` (bloqueia até decisão ou 120 s → `{"aprovado": bool}`); `POST /api/fechar`. POST com `Origin` diferente de `http://127.0.0.1:8766` → 403; sem `application/json` → 415.
  - `class Cerebro`: `publicar(evento: dict)` (para todas as conexões SSE), `mensagem_usuario(texto: str, falada: bool)` (prefixo `[voz] ` se falada; fala em curso é parada; se o Claude está ocupado, entra na fila de entrada), `super_j()`, `decidir_cartao(id, decisao)`, `pedir_permissao(ferramenta, entrada) -> bool` (espera até `ESPERA_PERMISSAO_S = 120`), `ao_evento_claude(evento: dict)` (deltas → `delta` + `SeparadorFala`; `result` → `resposta_fim`; `jarvis_reiniciando` → estado `desconectado`), atributo `bloqueada: Callable[[], bool]` (padrão `escuta.tela_bloqueada`), `laco_uma_vez()` e `laco()` (repete `laco_uma_vez` a cada 1 s). Cada `laco_uma_vez`: atualiza `sessoes` lendo `dados/vigia-estado.json`; publica pendências novas como `cartao`; se a tela está bloqueada, só coleta eventos; ao desbloquear com fila não vazia envia `"[sistema] O senhor voltou. Resuma em uma fala curta o que aconteceu enquanto esteve fora:\n" + linhas`; com Claude livre: primeiro a fila de entrada do usuário, depois eventos como `"[eventos]\n" + linhas`.
  - Eventos SSE publicados: `{"tipo":"estado","valor":...}`, `{"tipo":"nivel","valor":float}`, `{"tipo":"usuario","texto":..., "falada": bool}`, `{"tipo":"delta","texto":...}`, `{"tipo":"resposta_fim","texto":...}`, `{"tipo":"sessoes","itens":[{"projeto","worktree","estado","rotulo","mensagem"}]}`, `{"tipo":"cartao","id","tipo_pendencia","descricao"}`, `{"tipo":"cartao_fim","id","estado"}`, `{"tipo":"sistema","voz":bool,"orca":bool}`, `{"tipo":"historico","mensagens":[...]}`, `{"tipo":"aviso","texto"}` (aviso com a janela fechada).
  - Histórico: `dados/conversa.jsonl` (`{"em","papel":"usuario"|"jarvis","texto"}`), últimas 50 no `historico`.
  - Ao terminar uma resposta com pergunta de confirmação aberta (pendência criada no turno) e janela aberta, o cérebro reabre a escuta depois que a voz terminar (`/saude` com `falando: false`), por até 6 s.
  - `sessao/cerebro-settings.json`: allow `Bash(jarvis status:*)`, `Bash(jarvis historico:*)`, `Bash(jarvis clima:*)`, `Bash(jarvis enviar:*)`, `Bash(jarvis lancar:*)`, `Bash(jarvis regra:*)`, `Bash(jarvis confirmar:*)`, `Bash(jarvis recusar:*)`, `Bash(jarvis pendencias:*)`, `Bash(jarvis calar:*)`, `Bash(jarvis mudo:*)`, `Bash(orca worktree ps:*)`, `Bash(orca terminal read:*)`, `Bash(orca terminal list:*)`, `Bash(orca terminal show:*)`, `Bash(orca search:*)`, `Bash(orca repo list:*)`, `WebSearch`, `mcp__jarvis__permissao`; deny `Bash(orca terminal send:*)`, `Bash(orca agent launch:*)`, `Edit`, `Write`, `Read(//git/**/.env)`, `Read(//git/**/.env.*)`, `Read(//git/**/*.pem)`, `Read(//git/**/*.key)`, `Read(~/.ssh/**)`; `additionalDirectories: ["/git"]`; `enabledPlugins` com `caveman@caveman` e `superpowers@claude-plugins-official` false; sem hooks.
  - `sessao/CLAUDE.md`: troca "Ao iniciar"/Monitor por: mensagens `[eventos]` e `[sistema]` vêm do próprio app; ordens faladas para agentes, abrir agentes por voz e novas regras viram pendências (`jarvis enviar --origem voz`, `jarvis lancar --origem voz`, `jarvis regra adicionar`) e só se confirmam com `jarvis confirmar <id>` depois do "sim" do senhor; "roda o agente do X" → `jarvis lancar`; regras.md não se edita direto.
  - `jarvis cerebro` — sobe o servidor, o `ProcessoClaude` (`cwd=sessao/`, `PATH` com `bin/`), confere `orca status` e roda `orca open` se o app não estiver rodando, e roda `laco()`.

- [ ] **Step 1: Testes que falham** (com `ProcessoClaude` falso — objeto com `ocupado`, `enviar` gravando textos —, `tela_bloqueada` injetável e servidor em porta livre)

```python
def test_fila_filtra_tipos(dados_tmp):
    for tipo in ["sessao_aberta", "terminou", "orca_disponivel", "permissao"]:
        eventos.anexar(ev(tipo))
    f = FilaEventos(dados_tmp / "cerebro-cursor"); f.coletar()
    assert [l.split(":")[1].strip() for l in f.retirar()] == ["terminou", "pedindo permissão"]

def test_evento_espera_turno_do_usuario(cerebro_falso):
    c, claude = cerebro_falso
    c.mensagem_usuario("como estão os projetos?", falada=False)
    eventos.anexar(ev("terminou")); c.laco_uma_vez()
    assert claude.enviados == ["como estão os projetos?"]
    claude.ocupado = False; c.laco_uma_vez()
    assert claude.enviados[1].startswith("[eventos]\n")

def test_mensagem_durante_turno_vai_para_fila(cerebro_falso):
    c, claude = cerebro_falso
    c.mensagem_usuario("primeira", falada=False); c.mensagem_usuario("segunda", falada=True)
    assert claude.enviados == ["primeira"]
    claude.ocupado = False; c.laco_uma_vez()
    assert claude.enviados == ["primeira", "[voz] segunda"]

def test_tela_bloqueada_segura_e_resume(cerebro_falso):
    c, claude = cerebro_falso
    c.bloqueada = lambda: True
    eventos.anexar(ev("terminou")); c.laco_uma_vez()
    assert claude.enviados == []
    c.bloqueada = lambda: False; c.laco_uma_vez()
    assert claude.enviados[0].startswith("[sistema] O senhor voltou.")

def test_sse_recebe_historico_e_delta(servidor_cerebro):
    base, c = servidor_cerebro
    linhas = ler_sse(base + "/api/eventos", quantidade=2, depois=lambda: c.publicar({"tipo": "delta", "texto": "oi"}))
    assert linhas[0]["tipo"] == "historico" and {"tipo": "delta", "texto": "oi"} in linhas

def test_post_de_outra_origem_recusado(servidor_cerebro):
    base, _ = servidor_cerebro
    assert post(base + "/api/mensagem", {"texto": "x"}, origin="https://exemplo.com") == 403

def test_cartao_aprovado_confirma_pendencia(servidor_cerebro, dados_tmp, regras_tmp):
    base, c = servidor_cerebro
    p = pendencias.criar("regra", "x", {"texto": "y"})
    assert post(base + "/api/cartao", {"id": p["id"], "decisao": "aprovar"}, origin=None) == 200
    assert "- y" in regras_tmp.read_text()

def test_permissao_sem_resposta_nega(cerebro_falso, monkeypatch):
    c, _ = cerebro_falso
    monkeypatch.setattr(cerebro_main, "ESPERA_PERMISSAO_S", 0.2)
    assert c.pedir_permissao("Bash", {"command": "rm x"}) is False

def test_claude_reiniciando_publica_estado(cerebro_falso):
    c, _ = cerebro_falso
    publicados = []; c.publicar = publicados.append
    c.ao_evento_claude({"type": "jarvis_reiniciando"})
    assert {"tipo": "estado", "valor": "desconectado"} in publicados
```

- [ ] **Step 2: Rodar** → FAIL
- [ ] **Step 3: Implementar**
- [ ] **Step 4: Rodar a suíte inteira** → PASS
- [ ] **Step 5: Verificação real**: `bin/jarvis cerebro` num terminal; `curl -N localhost:8766/api/eventos` em outro; `curl -XPOST -H 'Content-Type: application/json' localhost:8766/api/mensagem -d '{"texto":"Jarvis, como estão os projetos?"}'` → deltas chegam no SSE, voz fala as linhas 🔊, `dados/conversa.jsonl` grava as duas mensagens. Encerrar.
- [ ] **Step 6: Commit** `feat: cérebro do Jarvis com Claude headless, fila de eventos e servidor da janela`

---

### Task 7: Gate visual, janela ligada ao cérebro e aviso com a janela fechada

**Files:**
- Modify: `hud/app.js`, `hud/estilo.css`, `hud/index.html`, `hud/janela.py`
- Create: `hud/aviso.html`, `tests/test_hud_aviso.py`

**Interfaces:**
- Consumes: SSE e rotas da Task 6.
- Produces:
  - `app.js` sem `?demo`: `EventSource("/api/eventos")`, reconexão automática; sem conexão por >2 s → `data-estado="desconectado"` com a mensagem "Jarvis desconectado. Tentando de novo…"; form envia `POST /api/mensagem`; botões dos cartões `POST /api/cartao`; Esc/clique no véu → `POST /api/fechar` + `fechar()`.
  - `hud/aviso.html`: faixa pequena e translúcida no estilo da janela, mostra o último `aviso`/frase falada por 6 s.
  - `hud/janela.py` cria uma segunda janela para o aviso: sem borda, transparente, canto superior direito, `set_accept_focus(False)`, `set_focus_on_map(False)`, `set_keep_above(True)`; aparece só quando a janela principal está escondida e chega um `aviso` (a página do aviso pede `"mostrar_aviso"`/`"esconder_aviso"` pelo `messageHandlers`).
- [ ] **Step 1: GATE — parar e mostrar ao usuário** a captura da Task 1 e `bin/jarvis hud --demo`; aplicar os ajustes visuais pedidos; seguir só com o visual aprovado.
- [ ] **Step 2: Testes que falham** (`tests/test_hud_aviso.py`)

```python
def test_aviso_existe_e_nao_rouba_foco():
    assert 'id="aviso"' in (RAIZ / "hud/aviso.html").read_text()
    py = (RAIZ / "hud/janela.py").read_text()
    assert "set_accept_focus(False)" in py and "set_focus_on_map(False)" in py

def test_app_reconecta_e_mostra_desconectado():
    js = (RAIZ / "hud/app.js").read_text()
    assert "EventSource" in js and "desconectado" in js and "Jarvis desconectado" in js
```

- [ ] **Step 3: Rodar** → FAIL
- [ ] **Step 4: Implementar**
- [ ] **Step 5: Rodar** → PASS. Real: `bin/jarvis cerebro` + `python3 hud/janela.py --mostrar` → conversa por texto funciona, sessões reais aparecem; parar o cérebro → janela mostra "Jarvis desconectado" e volta sozinha quando ele sobe; com a janela escondida, um `aviso` aparece no canto sem tirar o foco do terminal.
- [ ] **Step 6: Commit** `feat: janela do Jarvis ligada ao cérebro e aviso discreto`

---

### Task 8: Instalação, aposentar a aba do Orca e aceitação

**Files:**
- Create: `systemd/jarvis-cerebro.service`, `autostart/jarvis-hud.desktop`
- Modify: `jarvis/lancador.py` (instalar; `iniciar` → abre a janela), `jarvis/cli.py` (padrão = `hud`; remover `hook-fala`/`ouvir` do uso normal), `sessao/jarvis-settings.json` (removido), `README.md`, `tests/test_sessao_config.py`

**Interfaces:**
- Produces:
  - `systemd/jarvis-cerebro.service`: `ExecStart=/usr/bin/python3 /git/jarvis/bin/jarvis cerebro`, `Environment=PYTHONUNBUFFERED=1 PATH=%h/.config/orca/linux-orca-cli-shim:%h/.local/bin:/usr/local/bin:/usr/bin:/bin`, `After=jarvis-voz.service`, `Restart=always`, `WantedBy=default.target`.
  - `autostart/jarvis-hud.desktop`: `Exec=/usr/bin/python3 /git/jarvis/hud/janela.py`, `X-GNOME-Autostart-enabled=true`, `NoDisplay=true`.
  - `instalar()` copia também `jarvis-cerebro.service` (enable --now) e o `.desktop` para `~/.config/autostart/`; atalho `<Super>j` → `/git/jarvis/bin/jarvis hud`; `<Super><Shift>j` → `jarvis calar` (mantém).
  - `jarvis` sem argumentos = `jarvis hud`; `jarvis iniciar` deixa de abrir o Claude no terminal (imprime que o Jarvis agora é o app e chama `hud`).
- [ ] **Step 1: Testes que falham**

```python
def test_unidade_cerebro():
    u = (RAIZ / "systemd/jarvis-cerebro.service").read_text()
    assert "ExecStart=/usr/bin/python3 /git/jarvis/bin/jarvis cerebro" in u and "Restart=always" in u

def test_autostart_hud():
    d = (RAIZ / "autostart/jarvis-hud.desktop").read_text()
    assert "hud/janela.py" in d and "X-GNOME-Autostart-enabled=true" in d

def test_super_j_abre_hud():
    assert lancador.ATALHOS["jarvis-ouvir"][1].endswith("jarvis hud")

def test_sem_hook_de_fala_nem_monitor():
    s = json.loads((RAIZ / "sessao/cerebro-settings.json").read_text())
    assert "hooks" not in s and "Monitor" not in s["permissions"]["allow"]
    assert not (RAIZ / "sessao/jarvis-settings.json").exists()
    assert "Monitor" not in (RAIZ / "sessao/CLAUDE.md").read_text()
```

- [ ] **Step 2: Rodar** → FAIL
- [ ] **Step 3: Implementar**; atualizar `README.md`.
- [ ] **Step 4: Suíte inteira** → PASS. `bin/jarvis instalar` → `jarvis-voz`, `jarvis-vigia`, `jarvis-cerebro` ativos; `.desktop` em `~/.config/autostart/`; janela iniciada (`python3 hud/janela.py` rodando); `Super+J` → `/git/jarvis/bin/jarvis hud`.
- [ ] **Step 5: Commit** `feat: Jarvis como app sempre ligado (instalação e Super+J)`
- [ ] **Step 6: Aceitação com o usuário**, item a item do §10 da spec (inclusive reiniciar o PC). Corrigir o que falhar (com teste quando for lógica) e repetir.
