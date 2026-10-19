# Jarvis

Orquestrador por voz das sessões de agentes abertas no Orca. O cérebro é uma sessão do Claude Code com a persona do Jarvis; ele enxerga as outras sessões pela CLI do Orca, responde aos agentes conforme as suas ordens e regras, avisa quando algo muda e fala na voz clonada de `JarvisExample.mp3` (OmniVoice na GPU).

Design: `docs/superpowers/specs/2026-10-19-jarvis-orquestrador-design.md`.

## Instalar (uma vez)

```bash
/git/jarvis/bin/jarvis instalar
```

Instala e liga dois serviços do systemd do usuário, o comando `jarvis` em `~/.local/bin` e dois atalhos do GNOME:

- `jarvis-voz`: servidor de voz em `127.0.0.1:8765`, com OmniVoice e Whisper carregados na GPU (~4 GB de VRAM).
- `jarvis-vigia`: registra as mudanças das sessões do Orca em `dados/eventos.jsonl`.
- **Super+J** começa a gravar; apertar de novo envia o que você falou ao Jarvis.
- **Super+Shift+J** interrompe a fala.

## Usar

Abra um terminal no Orca e rode:

```bash
jarvis
```

O Jarvis registra o terminal dele e abre o Claude Code em `sessao/`, com persona, permissões e hook de voz. Depois ele cumprimenta você e passa a acompanhar os eventos sozinho. Uma sessão comum do Claude Code em `/git/jarvis` continua sendo uma sessão de desenvolvimento normal, sem voz e sem persona.

Exemplos:

- "Jarvis, o que está rodando?"
- "Bom dia, Jarvis." Ele traz clima, projetos e notícias de geopolítica, tecnologia, IA e crises financeiras.
- "Diz para o agente do app-analise-saude seguir com o plano." Numa ordem falada, ele confirma o destino e a mensagem antes de enviar.
- "A partir de agora, no app-analise-saude pode aprovar rodar testes." Vira uma regra em `sessao/regras.md`.
- "Silêncio" ou "modo mudo" (`jarvis calar`, `jarvis mudo on|off`).

## Comandos

| Comando | O que faz |
|---|---|
| `jarvis` / `jarvis iniciar` | abre a sessão do Jarvis (só num terminal do Orca) |
| `jarvis status [--json]` | estado de cada sessão de agente |
| `jarvis historico --desde 1d\|7d\|ISO` | eventos e commits por projeto |
| `jarvis clima` | clima agora em São Paulo (Open-Meteo) |
| `jarvis enviar ...` | envia mensagem/tecla a um agente; registra em `dados/acoes.jsonl` |
| `jarvis eventos --pendentes\|--seguir` | eventos do vigia |
| `jarvis ouvir` / `calar` / `mudo on\|off` | controles de voz |

## Onde ficam as coisas

- `sessao/CLAUDE.md`: persona e regras de comportamento.
- `sessao/jarvis-settings.json`: permissões, hook de voz e plugins desligados nesta sessão.
- `sessao/regras.md`: regras que você deu ao Jarvis.
- `dados/` (fora do git):
  - `eventos.jsonl`: eventos do vigia;
  - `acoes.jsonl`: tudo o que o Jarvis enviou a agentes;
  - `hook.log`: erros do hook de voz;
  - `voz/jarvis-prompt.pt`: a voz preparada a partir do MP3.
- Logs dos serviços: `journalctl --user -u jarvis-voz` e `journalctl --user -u jarvis-vigia`.

## Testes

```bash
python3 -m pytest -q
```
