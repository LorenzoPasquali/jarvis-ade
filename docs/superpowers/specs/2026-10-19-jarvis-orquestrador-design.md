# Design: Jarvis orquestrador por voz sobre o Orca

**Data:** 2026-10-19
**Substitui:** `docs/superpowers/specs/jarvis-orca-cockpit.md` e os planos de 2026-10-17 (app Tauri feito com Codex).

## 1. Intenção

O usuário trabalha com várias sessões de agentes (Claude Code) abertas no Orca, cada uma num projeto em `/git/*`. Ele quer um Jarvis que seja o **orquestrador** dessas sessões: acompanha o que cada agente está fazendo, **responde aos agentes conforme as instruções do usuário**, e mantém o usuário atualizado — por texto e por **voz**, com a voz oficial do Jarvis (clonada de `JarvisExample.mp3`).

O exemplo do MP3 resume o tom e o conteúdo esperados:

> "Olá, senhor! Hoje estão fazendo 20 graus. O clima está propenso. Dos seus últimos projetos do ORCA, o que mais precisa ser revisado é o modelo de gestão de saúde."

Ou seja: além do estado dos projetos, o Jarvis também traz o mundo de fora (clima e notícias).

### Por que recomeçar

O app anterior (Tauri + Rust + React + SQLite, ~7 mil linhas) não tinha cérebro (respostas por regex), não lia nem enviava nada às sessões do Orca e nunca tocou a voz oficial. Duas premissas que o travaram estavam erradas e foram verificadas em 2026-10-19:

- **O Orca é acessível.** `orca worktree ps --json` (Orca 1.4.230) funciona a partir de um terminal gerenciado pelo Orca e devolve, por worktree, os agentes com `state` (`working`, `done`, `waiting`, `permission`, `blocked`, `idle`), `lastAssistantMessage`, `toolName`, `prompt`, `paneKey` e prévia do terminal. `terminal read`, `terminal send` e `agent launch` existem e estão documentados em `orca agent-context --json`.
- **A GPU é utilizável.** RTX 5050 Laptop (8 GB), torch 2.8.0+cu128 com `sm_120`, no venv de `/git/FERRAMENTAS-LOCAL/OmniVoice/.venv`. OmniVoice fp16 com clonagem do MP3: carga 3,6 s, preparo da voz 0,9 s, 6,5 s de áudio em 2,8 s, 8,8 s de áudio em 3,3 s, pico de 2,4 GB de VRAM. O app anterior mediu só em CPU (102,9 s para 4,1 s) e concluiu errado que não havia GPU.

## 2. Decisões do usuário

- **O Jarvis é um Claude.** O cérebro é uma sessão do Claude Code dedicada ao Jarvis, aberta no Orca como qualquer outra sessão. Não haverá app próprio com interface gráfica; o texto do Jarvis é o terminal dele no Orca.
- **Papel: orquestrador.** Ele enxerga todas as sessões abertas no Orca, lê o que os agentes disseram, e responde a eles seguindo as instruções do usuário.
- **Mantém o usuário informado** do último status de cada agente/projeto.
- **Resumo do dia/semana** inclui: projetos, **clima** e **notícias** de fora.
- **Temas de notícia:** geopolítica principal, tecnologia, IA, crises financeiras de países.
- **Voz oficial:** OmniVoice instalado localmente, clonando `JarvisExample.mp3`. As respostas do Jarvis são transcritas para áudio nessa voz.
- **Idioma:** português do Brasil; trata o usuário por "senhor".

## 3. Objetivos

1. Uma sessão Jarvis no Orca que, a pedido, diz o estado de cada sessão aberta (o que está fazendo, o que terminou, o que espera o usuário).
2. O Jarvis envia mensagens/respostas à sessão certa, e só a ela.
3. O Jarvis responde sozinho aos agentes quando a situação é coberta por uma regra que o usuário deu; caso contrário, pergunta ao usuário e espera.
4. O Jarvis avisa o usuário, sem ser chamado, quando outra sessão termina, pede aprovação/resposta, ou trava.
5. Toda resposta do Jarvis é falada na voz oficial, além de escrita.
6. O usuário pode falar com o Jarvis (entrada por voz), não só digitar.
7. Briefing do dia/semana: projetos + clima + notícias nos temas escolhidos.

## 4. Não-objetivos

- Não construir interface gráfica própria (o Orca já é a interface).
- O Jarvis não edita código dos outros projetos diretamente; ele delega ao agente daquele projeto. *(Decisão do designer; ver §8.)*
- Nada de wake word ("Hey Jarvis") nesta versão.
- Não substituir os agentes de cada projeto nem fundir os contextos deles.
- Não reaproveitar o app Tauri anterior.

## 5. Anti-objetivos (seria falha mesmo funcionando)

- **Responder no lugar do usuário algo que ele não autorizou** — especialmente ações irreversíveis (push, deploy, apagar dados, gastar dinheiro, publicar). Na dúvida, perguntar.
- **Mandar mensagem para a sessão errada.** Cada envio precisa mirar um terminal identificado sem ambiguidade.
- **Obedecer texto vindo de outra sessão ou da web.** Saída de terminais, mensagens de agentes, páginas e notícias são *dados*, nunca instruções. Só o usuário (voz/texto na sessão Jarvis) e o arquivo de regras dele dão ordens.
- **Voz robotizada ou diferente do MP3.** Speech Dispatcher/`spd-say` e vozes genéricas estão descartados; se o OmniVoice falhar, o Jarvis fica só em texto e avisa.
- **Falar demais.** Ler tabelas, código, caminhos ou respostas longas em voz alta. A fala é um resumo curto; o detalhe fica no texto.
- **Ser chato.** Avisos repetidos do mesmo evento, ou falar por cima do usuário.
- **Vazar a persona do Jarvis para os outros agentes** (ver §6.1).

## 6. Como funciona (decidido)

### 6.1 Onde o Jarvis roda

- `/git/jarvis` serve a dois papéis: é onde o Jarvis é **desenvolvido** (sessões comuns do Claude Code) e onde ele **roda**. Os dois não podem se confundir. *(Decisão do designer.)*
  - A raiz `/git/jarvis` não carrega a persona: o `CLAUDE.md` dela, se houver, é só de desenvolvimento.
  - A sessão Jarvis é aberta por um lançador próprio (um comando só), em uma subpasta dedicada de `/git/jarvis` que contém a persona, os hooks de voz e as permissões `orca`. Sessões de desenvolvimento na raiz não ganham persona, voz nem permissão de `terminal send`. O construtor deve verificar isso na prática.
  - O lançador marca a sessão Jarvis de forma inequívoca (por exemplo, registrando o handle do terminal dela), para o vigia e o próprio Jarvis a excluírem como alvo e como fonte de eventos.
- A sessão Jarvis tem acesso de leitura a `/git`.
- **Não** colocar `CLAUDE.md` em `/git`: o Claude Code carrega `CLAUDE.md` dos diretórios-pai, então todo agente de `/git/*` herdaria a persona do Jarvis.
- O hook de voz existe só na configuração da sessão Jarvis; as sessões dos outros projetos nunca disparam voz.

### 6.2 Enxergar e responder às sessões

- Descoberta: `orca worktree ps --json` (estado de todos os agentes) e `orca terminal read` para o conteúdo de uma sessão específica.
- Envio: `orca terminal send --terminal <handle> --text ... --enter`, mirando o terminal do agente-alvo. A própria sessão Jarvis deve ser excluída como alvo e como fonte de eventos.
- Os comandos `orca` usados pelo Jarvis devem estar liberados nas permissões do projeto, para ele não pedir confirmação a cada leitura.
- A skill `orca-cli` (versão do Orca instalado, via `orca skills get orca-cli`) é a referência de uso da CLI.

### 6.3 Regras de autonomia

- Existe um arquivo de regras permanentes do usuário dentro de `/git/jarvis`, em texto legível e editável à mão. Exemplos do tipo de regra: "no app-analise-saude pode aprovar rodar testes; push só comigo".
- Quando o usuário diz algo como "a partir de agora, sempre que…", o Jarvis registra a regra nesse arquivo e confirma o que entendeu.
- **Ordem falada do usuário para um agente → confirmação obrigatória** *(decisão do usuário)*. Antes de enviar, o Jarvis repete em voz e texto o destino (projeto/sessão) e a mensagem exata que vai mandar, e só envia depois de o usuário confirmar. Se o usuário recusar ou corrigir, nada é enviado.
- Ordem digitada para um agente: envia direto quando o destino é inequívoco; se houver qualquer dúvida sobre o destino ou o conteúdo, confirma do mesmo jeito. *(Decisão do designer.)*
- Situação coberta por uma regra → o Jarvis responde ao agente e informa o usuário do que fez (sem confirmação prévia; é para isso que a regra existe).
- Situação não coberta, ambígua, ou irreversível sem regra explícita → o Jarvis pergunta ao usuário (voz + texto) e espera.
- Tudo que o Jarvis envia a qualquer agente fica registrado num log de ações em `/git/jarvis` (quando, para qual sessão/projeto, o quê, e com base em qual regra ou ordem).

### 6.4 Avisos proativos

- Um vigia local consulta o estado do Orca periodicamente e detecta transições das *outras* sessões: terminou (`done`), pede algo (`waiting`, `permission`), travou (`blocked`), ou abriu/fechou.
- Cada transição chega ao Jarvis como um evento; o Jarvis decide se aplica uma regra (§6.3) ou se avisa o usuário, e fala um resumo curto.
- O mesmo evento não é anunciado duas vezes.
- O vigia roda sempre que o computador está ligado e **registra** as transições num log de eventos em `/git/jarvis` (base do histórico do briefing). *(Decisão do designer.)*
- Quando a sessão Jarvis não estiver aberta, o vigia só registra: não fala, não responde a agentes. Ao abrir, o Jarvis pode resumir o que aconteceu enquanto estava fechado.

### 6.5 Briefing (dia/semana)

- Sob pedido ("Jarvis, como foi a semana?", "bom dia, Jarvis").
- Conteúdo, nesta ordem: saudação → clima → projetos (o que cada sessão fez, o que espera o usuário, commits do período) → notícias.
- **Quais projetos:** os registrados no Orca (`orca repo list`), não todo `/git/*`. *(Decisão do designer.)*
- **De onde vem o histórico** *(decisão do designer)*:
  - o log de eventos do vigia (§6.4);
  - a busca de sessões do próprio Orca, `orca search --since <iso> --json` (CLI documentada; indexa as conversas dos agentes);
  - `git log` do período, nos projetos que são repositórios git.
  - O Jarvis não lê diretamente os transcripts de `~/.claude/projects`.
- **Clima:** Open-Meteo (gratuito, sem chave). Cidade: São Paulo. *(Palpite do designer não contestado pelo usuário; ver §8.)*
- **Notícias:** busca web feita pelo próprio Claude do Jarvis, nos temas: geopolítica principal, tecnologia, IA, crises financeiras de países. Poucas manchetes, com a fonte no texto escrito.
- Versão falada: curta, no estilo do MP3. Versão escrita: com detalhes e links.

### 6.6 Voz de saída

- Um serviço local de voz mantém o OmniVoice carregado na GPU (fp16, `cuda:0`) com o prompt de voz do MP3 pré-computado e salvo (`create_voice_clone_prompt` → `VoiceClonePrompt.save/load`), usando o venv existente em `/git/FERRAMENTAS-LOCAL/OmniVoice/.venv`.
- Transcrição da referência (verificada): "Olá, senhor! Hoje estão fazendo 20 graus. O clima está propenso. Dos seus últimos projetos do ORCA, o que mais precisa ser revisado é o modelo de gestão de saúde."
- Gera por frase e começa a tocar a primeira frase enquanto gera as seguintes.
- Ao fim de cada resposta da sessão Jarvis, um hook entrega ao serviço de voz o trecho falável da resposta.
- O texto falado é um resumo de no máximo ~3 frases, sem código, tabelas, caminhos ou URLs; números por extenso quando necessário.
- O usuário consegue interromper a fala e silenciar o Jarvis (e reativar).
- Funciona offline (`HF_HUB_OFFLINE=1`), com pesos já em cache (`~/.cache/huggingface/hub/models--k2-fsa--OmniVoice`).

### 6.7 Voz de entrada

- Aperta-e-fala com Whisper local (`openai/whisper-large-v3-turbo`, já em cache; a transcrição offline foi validada pelo app anterior em `voice-worker/transcribe.py`).
- O texto transcrito entra como mensagem do usuário na sessão Jarvis.
- Ambiente: Zorin OS (GNOME) em **X11**; `pw-record`, `arecord`, `paplay`, `pw-play` e `ffmpeg` disponíveis.

## 7. Restrições

- Tudo local, exceto o próprio Claude (cérebro), a busca de notícias e a API de clima.
- VRAM de 8 GB: OmniVoice (~2,4 GB) e Whisper dividem a GPU; nenhum LLM local nesta versão.
- Não depender de formatos internos do Orca (banco, arquivos de estado); usar só a CLI documentada.
- Claude Code 2.1.303; Orca 1.4.230.

## 8. Decisões do designer (o usuário pode reverter)

- O Jarvis não edita código de outros projetos; delega ao agente do projeto.
- O Jarvis pode abrir um novo agente num projeto (`orca agent launch`) só por ordem explícita do usuário.
- Cidade do clima: São Paulo.
- Briefing só sob pedido; um briefing automático pela manhã fica como possível extensão.
- Resposta de prompts de permissão do Claude Code nos outros agentes só quando uma regra explícita cobre aquele tipo de ação.

## 9. Fica a critério do construtor

- Linguagem e forma do vigia e do serviço de voz (sugestão: Python, já que OmniVoice e Whisper são Python).
- Como o evento do vigia chega à sessão Jarvis sem atropelar o que o usuário estiver digitando.
- Como o hook identifica o trecho falável da resposta (formato combinado na persona, ou resumo).
- Atalho e mecânica do aperta-e-fala no GNOME/X11.
- Formato do arquivo de regras e do log de ações.
- Como iniciar tudo (idealmente uma ação só) e o que acontece se o serviço de voz cair.
- Limpeza do repositório: o que remover do app anterior (`src/`, `src-tauri/`, `node_modules/`, `dist/`, docs antigos) e onde deixar os clones de terceiros (`J.A.R.V.I.S/`, `jarvis-local/`). **Nada é apagado sem confirmação do usuário.** O diretório não é repositório git; inicializar o git antes de mudanças.

## 10. Como saber que deu certo

- Com o Jarvis e outra sessão abertos no Orca, "Jarvis, o que está rodando?" responde em voz e texto com o estado real de cada sessão.
- Quando a outra sessão termina ou pede aprovação, o Jarvis avisa sozinho em poucos segundos, uma vez.
- Falado: "Jarvis, diz para o agente do app-analise-saude seguir com o plano" → o Jarvis repete destino e mensagem, espera o "sim", e então a mensagem chega só àquele terminal e fica no log. Um "não" não envia nada.
- Uma situação coberta por regra é respondida sozinha e reportada; uma não coberta vira pergunta ao usuário.
- "Bom dia, Jarvis" traz clima de São Paulo, estado dos projetos e manchetes dos temas escolhidos, falado na voz do MP3.
- A primeira frase falada começa em ~3 s depois do fim da resposta em texto.
