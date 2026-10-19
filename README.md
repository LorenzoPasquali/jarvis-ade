# Jarvis

Orquestrador por voz das sessões de agentes abertas no Orca. O cérebro é uma sessão do Claude Code com a persona do Jarvis; ele enxerga as outras sessões pela CLI do Orca, responde aos agentes conforme as suas ordens e regras, avisa quando algo muda e fala na voz clonada de `JarvisExample.mp3` (OmniVoice na GPU).

Design: `docs/superpowers/specs/2026-10-19-jarvis-app-hud-design.md` (sobre `docs/superpowers/specs/2026-10-19-jarvis-orquestrador-design.md`).

## Instalar (uma vez)

```bash
/git/jarvis/bin/jarvis instalar
```

Liga três serviços do systemd do usuário, a janela no login, o comando `jarvis` em `~/.local/bin` e os atalhos do GNOME:

- `jarvis-voz`: servidor de voz em `127.0.0.1:8765`, com OmniVoice e Whisper carregados na GPU (~4 GB de VRAM).
- `jarvis-vigia`: registra as mudanças das sessões do Orca em `dados/eventos.jsonl`.
- `jarvis-cerebro`: o Jarvis em si. Mantém um Claude Code sem interface (modelo `sonnet`, ou o que estiver em `JARVIS_MODELO`), recebe as falas e os eventos e serve a janela em `127.0.0.1:8766`. Se o Orca estiver fechado, ele o abre.
- A janela (`hud/janela.py`) sobe escondida no login, pelo `~/.config/autostart/jarvis-hud.desktop`.
- **Super+J** abre a janela já ouvindo. Quando você para de falar, ele envia; Super+J de novo encerra na hora. Esc fecha.
- **Super+Shift+J** interrompe a fala.

## Usar

Aperte **Super+J** e fale, ou digite na caixa. Não precisa abrir o Orca nem um terminal.

- No centro fica o núcleo do Jarvis, que mostra se ele está ouvindo, pensando ou falando. Em volta, em órbita, ficam as sessões dos agentes, e quem precisa de você aparece em âmbar.
- Uma ordem falada para um agente, uma nova regra ou um pedido de permissão vira um cartão com botões. Também dá para responder "sim" ou "não" por voz.
- Com a janela fechada, ele continua avisando por voz, com uma faixa discreta no canto da tela que não tira o foco.
- Com a tela bloqueada, ele fica quieto. Quando você voltar, faz um resumo do que aconteceu.

Exemplos:

- "Jarvis, como estão os projetos?"
- "Bom dia, Jarvis." Ele traz clima, projetos e notícias de geopolítica, tecnologia, IA e crises financeiras.
- "Roda o agente do dailytracker para rodar os testes."
- "A partir de agora, no app-analise-saude pode aprovar rodar testes."
- "Silêncio" ou "modo mudo".

## Comandos

| Comando | O que faz |
|---|---|
| `jarvis` / `jarvis hud` | abre a janela e começa a ouvir |
| `jarvis hud --demo` | a janela com dados de exemplo, sem o cérebro |
| `jarvis status [--json]` | estado de cada sessão de agente |
| `jarvis lancar --projeto P --tarefa T --origem texto` | dá uma tarefa ao agente do projeto: usa a sessão parada ou abre uma nova |
| `jarvis pendencias` / `confirmar <id>` / `recusar <id>` | ações aguardando aprovação |
| `jarvis regra adicionar "<regra>"` / `regra remover <n>` | regras do que o Jarvis pode fazer sozinho |
| `jarvis historico --desde 1d\|7d\|ISO` | eventos e commits por projeto |
| `jarvis clima` | clima agora em São Paulo |
| `jarvis calar` / `mudo on\|off` | controles de voz |

## Onde ficam as coisas

- `hud/`: interface (HTML, CSS e JS), fontes locais e `janela.py`.
- `jarvis/cerebro/`: cérebro (Claude headless, fala, escuta, eventos, servidor da janela).
- `sessao/CLAUDE.md`: persona. `sessao/cerebro-settings.json`: permissões do cérebro. `sessao/regras.md`: suas regras.
- `dados/` (fora do git):
  - `conversa.jsonl`: histórico;
  - `eventos.jsonl`: eventos do vigia;
  - `acoes.jsonl`: tudo o que foi enviado aos agentes;
  - `pendencias.json`: ações aguardando aprovação;
  - `voz/jarvis-prompt.pt`: a voz preparada a partir do MP3.
- Logs: `journalctl --user -u jarvis-cerebro`, `-u jarvis-voz` e `-u jarvis-vigia`.

## Testes

```bash
python3 -m pytest -q
```
