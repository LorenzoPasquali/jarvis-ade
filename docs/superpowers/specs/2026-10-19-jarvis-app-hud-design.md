# Design: Jarvis como app autônomo com HUD (Super+J)

**Data:** 2026-10-19
**Evolui:** `docs/superpowers/specs/2026-10-19-jarvis-orquestrador-design.md` (o orquestrador já construído no branch `jarvis-orquestrador`). Tudo daquele design continua valendo, exceto onde este documento substitui: a conversa sai da aba do Orca e vai para um app próprio.

## 1. Intenção

O usuário testou o Jarvis rodando numa aba do Orca. Ele funcionou: chegou a avisar sozinho, na outra aba, quando uma sessão respondeu, e o usuário apontou isso como positivo. Mas não é o que ele quer no dia a dia. Nas palavras dele:

> "Eu ligo o meu PC, eu aperto o Windows J, já parece uma interface super design muito top, assim com CSS, transparência. Algo bem forte, assim mesmo, e eu só falo pro Jarvis como é que tá os projetos, mesmo sem abrir o Orca, mesmo sem ver nada, e ele já começa a me responder. […] mais autônomo, mais simples."

Também pediu: "que eu peça para ele ir rodando os agentes de cada pasta e ir me atualizando assim que tiver resposta".

O Jarvis vira um **app próprio, sempre ligado**: o cérebro roda em segundo plano desde o login, e **Super+J** abre uma interface translúcida, com visual forte de Jarvis, onde o usuário fala ou digita e ouve a resposta.

## 2. Decisões do usuário

- O Jarvis fica disponível assim que o PC liga, sem abrir o Orca nem um terminal.
- **Super+J** abre o app do Jarvis: interface de design forte, com CSS, **transparência sobre a tela** e "design gráfico de Jarvis mesmo".
- Conversa por **voz e texto** dentro dessa interface; respostas em voz (voz oficial do MP3) e texto.
- O usuário pode pedir para o Jarvis **rodar os agentes de cada pasta** e ser atualizado assim que eles responderem.
- O Jarvis continua proativo (avisar sozinho quando uma sessão termina/pede algo foi aprovado como positivo).
- Playback aprovado pelo usuário: abre já ouvindo; Esc/Super+J fecha e ele continua trabalhando; a janela mostra a conversa e as sessões; confirmações viram botões na janela; o Orca continua por baixo; a aba Jarvis do Orca deixa de ser necessária.
- Continuam valendo do design anterior: confirmação de ordem falada antes de enviar a um agente, regras do usuário, clima de São Paulo, notícias (geopolítica principal, tecnologia, IA, crises financeiras de países), envio seguro só a sessões de agentes, voz OmniVoice clonando `JarvisExample.mp3`.

## 3. Objetivos

1. Ao fazer login, o Jarvis (cérebro, voz, vigia e a janela escondida) já está rodando, sem nenhuma ação do usuário.
2. **Super+J** mostra a janela por cima de qualquer coisa, já ouvindo. O usuário fala; ao parar de falar, a fala é transcrita, aparece na conversa e vai ao Jarvis. Também dá para digitar.
3. A resposta aparece na janela enquanto é escrita, e a voz começa assim que a primeira frase falável estiver pronta.
4. A janela mostra as sessões de agentes do Orca (projeto, estado, última mensagem, quem espera o usuário) atualizadas sozinhas.
5. O usuário pede "roda o agente do <projeto> para <tarefa>" e o Jarvis abre um agente naquela pasta pelo Orca, acompanha, e avisa quando ele responder.
6. Com a janela fechada, o Jarvis continua: avisos proativos chegam por voz e por um sinal visual discreto no estilo da interface.
7. Confirmações (ordem falada para agente, nova regra, pedido de permissão que o Jarvis não pode decidir sozinho) aparecem como botões na janela e também aceitam "sim"/"não" por voz.

## 4. Não-objetivos

- Não reescrever o que já funciona: ferramentas `jarvis status/enviar/historico/clima/eventos`, vigia, servidor de voz e regras são reaproveitados.
- Não substituir o Orca como lugar onde os agentes rodam; ele continua por baixo.
- Sem wake word ("Hey Jarvis") nesta versão: a entrada de voz começa pelo Super+J (ou botão na janela).
- Sem versão mobile/web remota.

## 5. Anti-objetivos (falha mesmo funcionando)

- **Visual genérico.** Uma janela comum com cara de chat/SaaS, ou um "painel de admin", falha o pedido. Tem que parecer o Jarvis, ser translúcida sobre a tela e ter impacto.
- **Precisar do terminal/Orca para conversar.** Se o usuário tiver de abrir o Orca ou um terminal para falar com o Jarvis, falhou.
- **Lento ou travado.** Janela que demora a aparecer, ou silêncio longo sem nenhum sinal de que ele ouviu/está pensando.
- **Ruído.** Falar por cima do usuário, repetir avisos, roubar o foco do que o usuário está fazendo quando a janela está fechada.
- Todos os anti-objetivos do design anterior continuam (agir sem autorização, sessão errada, obedecer texto de terminais/web, voz robotizada, vazar persona).

## 6. Como funciona

### 6.1 Peças

- **Cérebro (`jarvis-cerebro`, serviço systemd do usuário):** mantém um processo do **Claude Code CLI em modo headless com streaming** (`claude -p --input-format stream-json --output-format stream-json --include-partial-messages`), com a persona e as permissões do Jarvis, usando o login do Claude Code do próprio usuário. *(Decisão do designer: o Agent SDK foi descartado porque a documentação pede chave de API e não permite login do claude.ai em produtos com o SDK; o CLI headless é o próprio Claude Code do usuário.)*
  - Recebe mensagens do usuário (da janela ou da voz) e eventos do vigia, e os entrega ao Claude.
  - Lê os eventos do vigia diretamente de `dados/eventos.jsonl` (substitui a ferramenta `Monitor` da aba do Orca) e os entrega ao Claude quando ele estiver livre, sem atropelar uma conversa em andamento.
  - Transmite o texto da resposta para a janela enquanto chega e manda as linhas `🔊` para o servidor de voz assim que cada uma termina.
  - Guarda o histórico da conversa em `dados/` para a janela mostrar ao reabrir, e retoma a mesma sessão do Claude depois de um reinício.
  - Serve a interface e uma conexão local (HTTP/WebSocket em 127.0.0.1) para a janela; recusa chamadas de páginas web (mesma regra do servidor de voz).
- **Formato da janela (decisão do usuário): tela inteira.** Um véu translúcido cobre toda a tela (1680x1050), deixando a área de trabalho visível ao fundo; o núcleo do Jarvis no centro, sessões de um lado, conversa e caixa de texto embaixo, cartões de confirmação no fluxo da conversa. Enquanto aberta, ela é a janela ativa; Esc ou clicar fora do conteúdo fecha.
- **Janela (`jarvis-hud`):** janela GTK 3 + WebKit2 4.1 (verificados na máquina: WebKit2 4.1, visual RGBA e compositor ativos), sem borda, **fundo transparente**, sempre por cima, fora da barra de tarefas. Mostra a interface web servida pelo cérebro. Inicia no login escondida (autostart do GNOME).
- **Servidor de voz (`jarvis-voz`):** continua como está (OmniVoice + Whisper na GPU).
- **Vigia (`jarvis-vigia`):** continua como está.

### 6.2 Super+J e a entrada de voz

- O atalho Super+J do GNOME passa a chamar `jarvis hud` (substitui `jarvis ouvir`).
- Janela escondida → aparece por cima, com foco, e começa a ouvir.
- A gravação acontece no lado do serviço (como o `pw-record` atual), não no navegador; o nível do microfone é enviado à janela para animar a interface.
- A gravação termina quando o usuário para de falar (silêncio de ~1 s) ou aperta Super+J de novo. Enquanto grava, o Jarvis não fala (fala em curso é interrompida).
- O texto transcrito aparece na conversa e vai ao cérebro como fala do usuário (marcado como falado, para valer a regra de confirmação).
- Super+J significa sempre "falar com o Jarvis": janela fechada → abre e ouve; ouvindo → encerra e envia; aberta e parada → volta a ouvir. **Esc** fecha a janela (sem perder nada). *(Decisão do designer; resolve a ambiguidade com a seção 2.)*
- Quando o Jarvis termina de falar uma pergunta de confirmação com a janela aberta, o microfone reabre sozinho por alguns segundos para o "sim"/"não" — só depois que a fala acabou, para o Whisper não ouvir a própria voz do Jarvis. *(Decisão do designer.)*
- Digitar na caixa de texto envia como mensagem digitada.

### 6.3 Proatividade com a janela fechada

- Eventos do vigia continuam chegando ao Jarvis; o que ele decidir falar sai em voz.
- Um sinal visual discreto no estilo da interface (ex.: um indicador pequeno no canto da tela com a última frase) aparece por alguns segundos, **sem roubar o foco** da janela que o usuário está usando.
- O que pede ação do usuário (pergunta, permissão, confirmação) fica marcado para quando ele abrir a janela.
- **Tela bloqueada** (usuário ausente): o cérebro não fala e não gasta turnos do Claude com eventos; eles ficam na fila. Ao desbloquear, o Jarvis faz um único resumo do que aconteceu. Respostas automáticas por regra também esperam o desbloqueio. *(Decisão do designer: evita falar para a sala vazia e gastar a cota dos agentes.)*
- Só eventos que pedem atenção viram turno do Claude: `terminou`, `aguardando`, `permissao`, `travou`, `orca_indisponivel`. `sessao_aberta`/`sessao_fechada`/`orca_disponivel` só atualizam o painel. *(Decisão do designer.)*

### 6.4 Confirmações e permissões

- Ordem falada para um agente: o Jarvis mostra um cartão com destino e mensagem exata e os botões Enviar/Cancelar; "sim"/"não" por voz também valem. Só envia após a confirmação (`jarvis enviar --origem voz --confirmado`).
- Nova regra: só fica ativa depois que o usuário aprova o cartão com o texto da regra.
- Ações que a persona/permissões não liberam: o Claude headless pede permissão por um mecanismo do próprio Claude Code (`--permission-prompt-tool`), que o cérebro transforma em cartão Aprovar/Recusar na janela. Sem resposta, nada acontece.
- Pedidos de permissão dos **outros agentes** seguem o fluxo já construído (regra explícita ou pergunta ao usuário; aqui, como cartão).

### 6.5 Rodar agentes nas pastas

- "Roda o agente do <projeto> para <tarefa>": *(decisão do designer)*
  - se o projeto já tem uma sessão de agente **parada** (concluiu/aguardando), a tarefa vai para ela (`jarvis enviar`);
  - se a sessão existente está **trabalhando**, o Jarvis pergunta se espera, manda mesmo assim ou abre outro agente;
  - se não há sessão, abre um agente na pasta do projeto: `orca agent launch --agent claude --worktree path:<pasta> --prompt "<tarefa>"`;
  - nunca cria worktrees/branches novos por conta própria.
  - Só por ordem do usuário; ordem falada passa pela confirmação.
- O agente novo aparece no painel de sessões; quando ele terminar ou perguntar algo, o vigia gera o evento e o Jarvis avisa (voz + sinal visual), com um resumo do que o agente respondeu.
- Precisa de uma nova ferramenta segura `jarvis lancar --projeto <nome> --tarefa <texto>` (registrada em `dados/acoes.jsonl`, resolvendo o projeto sem ambiguidade), no lugar de liberar `orca agent launch` direto.

### 6.6 Orca por baixo

- Ao iniciar, o cérebro confere `orca status`. Se o Orca não estiver rodando, abre-o (`orca open`). *(Decisão do designer.)*
- Se o Orca não puder ser alcançado, o Jarvis diz isso e continua respondendo o que não depende dele (clima, notícias, conversa).

### 6.7 Visual

- Direção dada pelo usuário: "design gráfico de Jarvis mesmo", "super design muito top", CSS, transparência, "algo bem forte".
- Construída com a skill `frontend-design` (plano de tokens, revisão contra o genérico, depois código).
- Elementos: um núcleo visual central do Jarvis que reage aos estados (ouvindo — com o nível do microfone —, pensando, falando, ocioso); a conversa; o painel de sessões; cartões de confirmação; a caixa de texto; o estado do sistema (voz, Orca).
- Fundo translúcido deixando ver a área de trabalho; legível sobre qualquer papel de parede.
- Texto da interface em pt-BR.
- **Gate:** o primeiro entregável é a janela real com o visual e dados de exemplo, para o usuário aprovar o visual antes de ligar tudo.

## 7. Restrições

- Linux Zorin OS (GNOME) em X11, compositor ativo; Python 3.12 do sistema com PyGObject, Gtk 3 e WebKit2 4.1.
- Claude Code 2.1.303 (flags headless verificadas: `--input-format stream-json`, `--output-format stream-json`, `--include-partial-messages`, `--permission-prompt-tool`, `--resume`, `--settings`, `--append-system-prompt`). Sem chave de API: usa o login do Claude Code do usuário via CLI.
- Orca 1.4.230 (`orca status`, `orca open`, `orca agent launch --agent --worktree --prompt` verificados).
- GPU de 8 GB: a voz já usa ~4 GB; a interface não pode depender de GPU além do compositor.
- Sem dependência que precise de chave ou serviço pago.
- Nada do app antigo do Codex é apagado sem confirmação do usuário (continua valendo).

## 8. Decisões do designer (o usuário pode reverter)

- Cérebro = Claude Code CLI headless com streaming (não Agent SDK).
- Janela = GTK + WebKit2 em Python (sem Electron/Tauri), interface em HTML/CSS/JS servida pelo cérebro.
- Gravação de voz no serviço, fim por silêncio ou novo Super+J.
- Se o Orca estiver fechado no login, o Jarvis o abre.
- Aviso com a janela fechada: voz + sinal visual discreto que não rouba o foco.
- `jarvis lancar` como ferramenta própria para abrir agentes.
- A aba Jarvis do Orca é aposentada: `jarvis iniciar`, o hook de fala e o `Monitor` saem; `jarvis` sem argumentos passa a abrir a janela. Assim não há dois cérebros lendo o mesmo cursor de eventos nem falando em dobro.
- Modelo do cérebro: **Sonnet** por padrão (resposta falada mais rápida e menos cota que o Opus dos agentes), configurável.
- Tela bloqueada: sem fala e sem turnos do Claude; resumo único ao desbloquear.
- "Roda o agente" reaproveita a sessão parada do projeto; não abre um segundo agente na mesma pasta sem perguntar.

## 9. A critério do construtor

- Protocolo exato entre janela e cérebro; formato do histórico.
- Como entregar eventos ao Claude sem atropelar a conversa (fila, agrupamento).
- Detecção de silêncio (parâmetros) e o sinal visual com a janela fechada.
- Modelo usado pelo cérebro (padrão: o mesmo do Claude Code do usuário; pode preferir um mais rápido para conversa se a latência pesar).
- Estrutura de arquivos da interface; animações (respeitando `prefers-reduced-motion`).
- Como o `--permission-prompt-tool` é implementado (servidor MCP local do próprio cérebro, por exemplo).

## 10. Como saber que deu certo

- Depois de reiniciar o PC, sem abrir nada, Super+J mostra a janela translúcida e já ouvindo em menos de 1 s.
- "Jarvis, como estão os projetos?" falado → texto aparece na janela enquanto ele responde, e a voz começa em poucos segundos.
- "Roda o agente do dailytracker para rodar os testes" → cartão de confirmação → ao confirmar, um agente abre no Orca naquela pasta; quando ele termina, o Jarvis avisa por voz com a janela fechada, sem roubar o foco.
- Um agente pede permissão → o aviso chega; ao abrir a janela, há um cartão para decidir.
- O usuário aprova o visual no gate antes da integração.
- Orca fechado no login → o Jarvis o abre; Orca inalcançável → o Jarvis avisa e continua respondendo o resto.
