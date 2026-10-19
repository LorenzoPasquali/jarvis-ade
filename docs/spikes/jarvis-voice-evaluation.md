# Avaliação de voz local do Jarvis

**Data:** 2026-10-17  
**Ambiente:** Linux x86_64, 31 GiB de RAM, sem GPU NVIDIA utilizável.  
**Rede:** testes executados com `HF_HUB_OFFLINE=1` e `TRANSFORMERS_OFFLINE=1`.

## Entrada de voz: Whisper local

- Pesos de `openai/whisper-large-v3-turbo` encontrados no cache local.
- O worker transcreveu o MP3 de referência para: “Olá, senhor! Hoje estão fazendo 20 graus. O clima está propenso. Dos seus últimos projetos do ORCA, o que mais precisa ser revisado é o modelo de gestão de saúde.”
- A transcrição foi feita offline. O MP3 bruto não é enviado a serviços remotos.
- **Decisão:** manter Whisper local no push-to-talk. A transcrição aparece no campo de texto para revisão antes do envio.

## Saída de voz: OmniVoice e amostra Jarvis

- OmniVoice está instalado em `/git/FERRAMENTAS-LOCAL/OmniVoice`; os pesos estavam em cache.
- Uma medição inicial gerou 3,6 segundos em 57,8 segundos, mas usou transcrição automática da referência e não verificou qualidade perceptual.
- A referência foi transcrita corretamente e a medição foi repetida com `ref_text` explícito, CPU, `float32`, 4 threads e 16 passos.
- Carregar o modelo levou 2,2 segundos; preparar a referência, 3,6 segundos; sintetizar 4,1 segundos de áudio levou 102,9 segundos.
- O CLI padrão do OmniVoice usa `float16` no CPU e não concluiu dentro de dois minutos; o processo foi interrompido.
- A nova amostra ficou em `/tmp/jarvis-omnivoice-correct-ref.wav` para revisão auditiva. A qualidade ainda não foi confirmada pelo usuário.
- **Decisão:** não usar OmniVoice como resposta falada interativa nesta máquina enquanto essa latência persistir.

## Fala genérica do sistema

- O app oferecia Speech Dispatcher (`spd-say`) como fallback.
- O usuário relatou que essa fala era robotizada e quebrada e não correspondia ao MP3.
- **Decisão:** removemos os controles e comandos de fala genérica. O Jarvis mantém entrada de voz por Whisper e saída em texto; a síntese volta apenas depois de uma avaliação de qualidade e latência da voz local baseada na referência.

## Alternativa encontrada no protótipo Python

- `/git/jarvis/jarvis-local` usa Pocket TTS com `get_state_for_audio_prompt()` e `generate_audio_stream()`, mantendo o modelo e o estado da voz carregados entre falas.
- O protótipo inclui benchmarks de streaming em CPU e amostras de voz, mas esses números não foram medidos nesta execução do Jarvis.
- A documentação oficial atual do [Pocket TTS](https://github.com/kyutai-labs/pocket-tts) confirma clonagem de voz, streaming e suporte a português. A [API Python oficial](https://kyutai-labs.github.io/pocket-tts/API%20Reference/python-api/) aceita `language="portuguese"`, converte áudio de referência em estado de voz e permite salvá-lo para reutilização.
- `pocket_tts` não está instalado no Python do sistema nem no ambiente virtual local do OmniVoice, e não encontrei os pesos no cache local desta execução.
- **Implementação no Jarvis:** Configurações agora oferece um preparo acionado pelo usuário. Ele instala Pocket TTS em um ambiente local de CPU, baixa o modelo português, prepara `JarvisExample.mp3` uma vez e guarda os pesos no cache local. Os pesos de clonagem são gated pela Hugging Face; a pessoa precisa aceitar as condições e informar um token de leitura temporário. O worker persistente sintetiza em `HF_HUB_OFFLINE=1`; o app não baixa nada ao iniciar nem durante as respostas.
- A tela de Configurações tem um botão “Testar voz”, e a conversa tem controles para ouvir cada resposta e ligar/desligar a leitura automática. A avaliação sonora e de latência ainda precisa ser feita pelo usuário na janela desktop, porque pacote e pesos não estão presentes nesta execução.

## Limites desta avaliação

- A captura real do microfone e a saída sintetizada continuam sem validação manual na janela do app.
- As medições de síntese não comprovam semelhança de voz; é preciso ouvir a amostra gerada.
- O arquivo de avaliação está fora do repositório e não é incluído no app.
