import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Icon } from "../../components/Icon";
import { getGitActivity, listProjectRoots } from "../../shared/api/projectRoots";
import { listChatMessages, saveChatMessage } from "../../shared/api/settings";
import { getPreference, setPreference } from "../../shared/api/preferences";
import {
  getLocalSpeechStatus,
  speakLocalText,
  transcribeLocalAudio,
  type LocalSpeechStatus,
} from "../../shared/api/voice";
import type { ChatMessage } from "../../shared/types/inbox";
import type { GitActivity } from "../../shared/types/project";
import type { OrcaConnection } from "../../shared/types/orca";

type View = "projects" | "inbox" | "settings";
type VoiceState = "idle" | "recording" | "transcribing";

interface InboxPageProps {
  connection: OrcaConnection | null;
  checkingConnection: boolean;
  onCheckConnection: () => void;
  onNavigate: (view: View) => void;
}

export default function InboxPage({
  connection,
  checkingConnection,
  onCheckConnection,
  onNavigate,
}: InboxPageProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSending, setIsSending] = useState(false);
  const [historyError, setHistoryError] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [speechStatus, setSpeechStatus] = useState<LocalSpeechStatus | null>(null);
  const [autoSpeak, setAutoSpeak] = useState(false);
  const [speechBusyId, setSpeechBusyId] = useState<string | null>(null);
  const [speakingId, setSpeakingId] = useState<string | null>(null);
  const [speechError, setSpeechError] = useState<string | null>(null);
  const endOfMessagesRef = useRef<HTMLDivElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const recordingTimeoutRef = useRef<number | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);
  const audioMessageIdRef = useRef<string | null>(null);

  useEffect(() => {
    let mounted = true;
    listChatMessages(100)
      .then((saved) => {
        if (!mounted) return;
        setMessages(saved);
        setIsLoading(false);
      })
      .catch(() => {
        if (!mounted) return;
        setHistoryError(true);
        setIsLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    let mounted = true;
    void getLocalSpeechStatus()
      .then((status) => {
        if (mounted) setSpeechStatus(status);
      })
      .catch(() => {
        if (mounted) setSpeechStatus({ ready: false, message: "Não consegui verificar a voz local." });
      });
    void getPreference("voice_auto_speak")
      .then((preference) => {
        if (mounted && preference !== null) setAutoSpeak(preference === "true");
      })
      .catch(() => undefined);
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    endOfMessagesRef.current?.scrollIntoView({ block: "end" });
  }, [messages, isSending]);

  useEffect(() => {
    const textarea = document.getElementById("jarvis-message");
    if (!(textarea instanceof HTMLTextAreaElement)) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 144)}px`;
  }, [draft]);

  useEffect(() => () => {
    if (recordingTimeoutRef.current !== null) window.clearTimeout(recordingTimeoutRef.current);
    const recorder = recorderRef.current;
    if (recorder?.state === "recording") {
      recorder.onstop = null;
      recorder.stop();
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    audioRef.current?.pause();
    if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
  }, []);

  const stopSpeech = () => {
    audioRef.current?.pause();
    audioRef.current = null;
    if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
    audioUrlRef.current = null;
    audioMessageIdRef.current = null;
    setSpeakingId(null);
    setSpeechBusyId(null);
  };

  const playSpeech = async (text: string, messageId: string) => {
    if (!speechStatus?.ready) {
      setSpeechError("Prepare a voz local em Configurações antes de ouvir as respostas.");
      return;
    }
    stopSpeech();
    setSpeechError(null);
    setSpeechBusyId(messageId);
    try {
      const bytes = await speakLocalText(text);
      const url = URL.createObjectURL(new Blob([new Uint8Array(bytes)], { type: "audio/wav" }));
      const audio = new Audio(url);
      audioRef.current = audio;
      audioUrlRef.current = url;
      audioMessageIdRef.current = messageId;
      const releaseAudio = () => {
        if (audioRef.current !== audio) return;
        audioRef.current = null;
        audioUrlRef.current = null;
        audioMessageIdRef.current = null;
        URL.revokeObjectURL(url);
        setSpeakingId(null);
      };
      audio.onended = releaseAudio;
      audio.onerror = () => {
        releaseAudio();
        setSpeechError("O áudio foi gerado, mas o dispositivo não conseguiu reproduzi-lo.");
      };
      setSpeechBusyId(null);
      setSpeakingId(messageId);
      await audio.play();
    } catch (error) {
      if (error instanceof DOMException && error.name === "NotAllowedError" && audioMessageIdRef.current === messageId) {
        setSpeakingId(null);
        setSpeechError("O áudio foi gerado. Toque em Ouvir resposta para iniciar a reprodução.");
        return;
      }
      stopSpeech();
      setSpeechError(getAppErrorMessage(error, "Não consegui gerar a fala local."));
    } finally {
      setSpeechBusyId(null);
    }
  };

  const toggleAutoSpeak = async () => {
    if (!speechStatus?.ready) {
      onNavigate("settings");
      return;
    }
    const next = !autoSpeak;
    setAutoSpeak(next);
    try {
      await setPreference("voice_auto_speak", String(next), new Date().toISOString());
    } catch {
      setAutoSpeak(!next);
      setSpeechError("Não consegui salvar a preferência de fala automática.");
    }
  };

  const submitMessage = async (event?: FormEvent) => {
    event?.preventDefault();
    const body = draft.trim();
    if (!body || isSending) return;

    setDraft("");
    setIsSending(true);
    setSendError(null);
    let userMessage: ChatMessage;
    try {
      userMessage = await saveChatMessage("user", body, new Date().toISOString());
    } catch {
      setSendError("Não consegui guardar sua pergunta localmente. Ela continua no campo de texto; tente novamente.");
      setDraft(body);
      setIsSending(false);
      return;
    }
    setMessages((current) => [...current, userMessage]);
    try {
      const replyBody = await answerFromLocalProjects(body, connection);
      const assistantMessage = await saveChatMessage("assistant", replyBody, new Date().toISOString());
      setMessages((current) => [...current, assistantMessage]);
      if (autoSpeak && speechStatus?.ready) void playSpeech(assistantMessage.body, assistantMessage.id);
    } catch {
      setSendError("Sua pergunta foi salva, mas não consegui consultar os dados locais agora. Tente enviar outra vez em alguns instantes.");
    } finally {
      setIsSending(false);
    }
  };

  const onComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void submitMessage();
    }
  };

  const toggleRecording = async () => {
    setVoiceError(null);
    if (voiceState === "recording") {
      if (recordingTimeoutRef.current !== null) window.clearTimeout(recordingTimeoutRef.current);
      if (recorderRef.current?.state === "recording") recorderRef.current.stop();
      setVoiceState("transcribing");
      return;
    }
    if (voiceState !== "idle") return;

    try {
      if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
        setVoiceError("Este ambiente do app não oferece captura de áudio. Use o campo de texto por enquanto.");
        return;
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
        video: false,
      });
      streamRef.current = stream;
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      const recorder = new MediaRecorder(stream, { mimeType });
      chunksRef.current = [];
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        recorderRef.current = null;
        const audio = new Blob(chunksRef.current, { type: recorder.mimeType || mimeType });
        chunksRef.current = [];
        try {
          if (audio.size < 128) throw new Error("empty_recording");
          const bytes = Array.from(new Uint8Array(await audio.arrayBuffer()));
          const transcript = await transcribeLocalAudio(bytes, audio.type);
          setDraft((current) => current.trim() ? `${current.trim()} ${transcript}` : transcript);
          window.requestAnimationFrame(() => document.getElementById("jarvis-message")?.focus());
        } catch (error) {
          setVoiceError(getAppErrorMessage(error, "A transcrição local falhou. Confira o modelo Whisper em cache e tente novamente."));
        } finally {
          setVoiceState("idle");
        }
      };
      recorder.start(250);
      setVoiceState("recording");
      recordingTimeoutRef.current = window.setTimeout(() => {
        if (recorder.state === "recording") recorder.stop();
        setVoiceState("transcribing");
      }, 45_000);
    } catch (error) {
      recorderRef.current = null;
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      const name = error instanceof DOMException ? error.name : "";
      setVoiceError(name === "NotAllowedError" || name === "PermissionDeniedError"
        ? "Permita o acesso ao microfone nas configurações do sistema e tente novamente."
        : "Não consegui iniciar o microfone. Confira se ele está conectado e disponível.");
    }
  };

  return (
    <div className="inbox-page">
      <section className="conversation-intro">
        <div>
          <span className="eyebrow">CENTRAL DO JARVIS</span>
          <h2>Seus projetos, numa conversa só.</h2>
          <p>Por enquanto, consulto as pastas locais que você cadastrou e o estado do Git. Ainda não leio nem respondo aos agentes do Orca.</p>
        </div>
        <button className="button button-secondary conversation-project-link" type="button" onClick={() => onNavigate("projects")}>
          <Icon name="projects" size={17} /> Ver projetos
        </button>
      </section>

      <section className={`connection-card${connection?.connected ? " is-connected" : ""}`} aria-labelledby="connection-title">
        <div className="connection-card-mark" aria-hidden="true"><Icon name="orbit" size={21} /></div>
        <div className="connection-card-copy">
          <div className="connection-card-heading">
            <h3 id="connection-title">{connection?.connected ? "CLI do Orca respondeu" : "Agentes do Orca não conectados"}</h3>
            <span className={`connection-label${connection?.connected ? " is-connected" : ""}`}>
              <span className="status-marker" /> {connection?.connected ? "CLI ACESSÍVEL" : checkingConnection ? "VERIFICANDO" : "DESCONECTADO"}
            </span>
          </div>
          <p>{checkingConnection ? "Testando o comando repo list do CLI. Isso não consulta worktrees, terminais ou sessões." : connection?.connected ? "O CLI respondeu, mas este Jarvis ainda não lista sessões nem encaminha mensagens a agentes." : connection?.message ?? "O Jarvis ainda não verificou se o CLI consegue acessar o Orca nesta sessão."}</p>
        </div>
        <button className="button button-quiet connection-check-button" type="button" onClick={onCheckConnection} disabled={checkingConnection}>
          {checkingConnection ? "Verificando…" : "Testar conexão"}
        </button>
      </section>

      <section className="conversation-panel" aria-label="Conversa com o Jarvis">
        <div className="conversation-scroll" aria-live="polite" aria-busy={isLoading || isSending}>
          {isLoading ? (
            <div className="conversation-loading" role="status">Carregando conversa local…</div>
          ) : historyError ? (
            <div className="conversation-loading is-error" role="alert">Não foi possível abrir o histórico local. Você ainda pode consultar os projetos nesta sessão.</div>
          ) : messages.length === 0 ? (
            <div className="conversation-welcome">
              <div className="welcome-mark"><Icon name="orbit" size={27} /></div>
              <h3>Olá. O que você quer saber?</h3>
              <p>Posso verificar quais pastas têm alterações locais no Git. Ainda não afirmo que um agente está trabalhando sem confirmação do Orca.</p>
              <div className="conversation-prompts">
                <button type="button" onClick={() => setDraft("Quais projetos estão em andamento?")}>Quais projetos estão em andamento?</button>
                <button type="button" onClick={() => setDraft("Quais projetos têm alterações no Git?")}>Quais projetos têm alterações no Git?</button>
                <button type="button" onClick={() => onNavigate("projects")}>Gerenciar minhas pastas</button>
              </div>
            </div>
          ) : (
            <div className="conversation-messages">
              {messages.map((message) => (
                <ConversationMessage
                  key={message.id}
                  message={message}
                  speechReady={speechStatus?.ready === true}
                  isGeneratingSpeech={speechBusyId === message.id}
                  isSpeaking={speakingId === message.id}
                  onSpeak={() => {
                    if (speakingId === message.id) {
                      stopSpeech();
                    } else if (audioMessageIdRef.current === message.id && audioRef.current) {
                      setSpeechError(null);
                      setSpeakingId(message.id);
                      void audioRef.current.play().catch((error: unknown) => {
                        setSpeakingId(null);
                        setSpeechError(getAppErrorMessage(error, "Não consegui reproduzir o áudio."));
                      });
                    } else {
                      void playSpeech(message.body, message.id);
                    }
                  }}
                />
              ))}
              {isSending && (
                <div className="chat-message assistant-message" role="status">
                  <span className="message-role">JARVIS · LOCAL</span>
                  <p>Consultando seus projetos…</p>
                </div>
              )}
              <div ref={endOfMessagesRef} />
            </div>
          )}
        </div>

        <form className="conversation-composer" noValidate onSubmit={(event) => void submitMessage(event)}>
          {sendError && <p className="conversation-error" role="alert">{sendError}</p>}
          {voiceError && <p className="conversation-error" role="alert">{voiceError}</p>}
          {speechError && <p className="conversation-error" role="alert">{speechError}</p>}
          <label className="sr-only" htmlFor="jarvis-message">Mensagem para o Jarvis</label>
          <textarea
            id="jarvis-message"
            className="resize-none"
            rows={2}
            maxLength={2000}
            value={draft}
            onChange={(event) => setDraft(event.currentTarget.value)}
            onKeyDown={onComposerKeyDown}
            placeholder="Pergunte sobre seus projetos locais…"
            disabled={isSending || isLoading}
          />
          <div className="composer-footer">
            <span className="composer-hint">Enter envia · Shift + Enter quebra linha</span>
            <div className="composer-actions">
              <button
                className={`button button-auto-speak${autoSpeak && speechStatus?.ready ? " is-active" : ""}`}
                type="button"
                onClick={() => void toggleAutoSpeak()}
                disabled={speechStatus === null}
                aria-pressed={autoSpeak && speechStatus?.ready === true}
                title={speechStatus?.ready ? "Ler automaticamente cada resposta do Jarvis usando a voz local." : "Preparar a voz Jarvis nas Configurações."}
              >
                <Icon name={autoSpeak && speechStatus?.ready ? "speaker" : "volume-off"} size={16} />
                <span>{speechStatus === null ? "Voz…" : speechStatus.ready ? `Fala ${autoSpeak ? "ligada" : "desligada"}` : "Preparar voz"}</span>
              </button>
              <button
                className={`button button-voice${voiceState === "recording" ? " is-recording" : ""}`}
                type="button"
                onClick={() => void toggleRecording()}
                disabled={voiceState === "transcribing" || isSending || isLoading}
                aria-pressed={voiceState === "recording"}
                aria-label={voiceState === "recording" ? "Encerrar ditado e transcrever" : voiceState === "transcribing" ? "Transcrevendo áudio localmente" : "Ditar pergunta por voz"}
                title="A gravação fica temporária e a transcrição roda localmente, sem enviar o áudio para um serviço remoto."
              >
                <Icon name="microphone" size={17} />
                <span>{voiceState === "recording" ? "Encerrar ditado" : voiceState === "transcribing" ? "Transcrevendo…" : "Ditar"}</span>
              </button>
              <button className="button button-primary" type="submit" disabled={!draft.trim() || isSending || isLoading}>
                {isSending ? "Consultando…" : "Enviar"} <Icon name="arrow-right" size={17} />
              </button>
            </div>
          </div>
          {voiceState === "recording" && <p className="voice-status" role="status">Gravando no dispositivo. Clique em Encerrar gravação quando terminar; limite de 45 segundos.</p>}
          {voiceState === "transcribing" && <p className="voice-status" role="status">Transcrevendo com Whisper local. O texto aparecerá aqui para você revisar antes de enviar.</p>}
          {speechBusyId && <p className="voice-status" role="status">Gerando áudio com a voz Jarvis local…</p>}
        </form>
        <p className="conversation-privacy">
          O áudio e a voz são processados neste dispositivo. {speechStatus?.ready ? "A fala automática pode ser ligada ou desligada acima." : "Para ouvir o Jarvis, abra Configurações e prepare a voz local uma vez."} Mensagens ainda não são encaminhadas a agentes.
        </p>
      </section>
    </div>
  );
}

function ConversationMessage({
  message,
  speechReady,
  isGeneratingSpeech,
  isSpeaking,
  onSpeak,
}: {
  message: ChatMessage;
  speechReady: boolean;
  isGeneratingSpeech: boolean;
  isSpeaking: boolean;
  onSpeak: () => void;
}) {
  const isAssistant = message.role === "assistant";
  const time = new Intl.DateTimeFormat("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "America/Sao_Paulo",
  }).format(new Date(message.createdAt));

  return (
    <article className={`chat-message ${isAssistant ? "assistant-message" : "user-message"}`}>
      <span className="message-role">{isAssistant ? "JARVIS · LOCAL" : "VOCÊ"} <time dateTime={message.createdAt}>{time}</time></span>
      <p>{message.body}</p>
      {isAssistant && speechReady && (
        <button className="message-speak-button" type="button" onClick={onSpeak} disabled={isGeneratingSpeech}>
          <Icon name={isSpeaking ? "volume-off" : "speaker"} size={14} />
          {isGeneratingSpeech ? "Gerando áudio…" : isSpeaking ? "Parar leitura" : "Ouvir resposta"}
        </button>
      )}
    </article>
  );
}

function getAppErrorMessage(error: unknown, fallback: string): string {
  if (error && typeof error === "object" && "message" in error && typeof error.message === "string") {
    return error.message;
  }
  return fallback;
}

async function answerFromLocalProjects(question: string, connection: OrcaConnection | null): Promise<string> {
  const asksAboutProjects = /projet|pasta|git|altera|commit|branch|atividade|andamento/i.test(question);
  if (!asksAboutProjects) {
    return "Por enquanto, respondo perguntas sobre pastas locais e sinais do Git. A conexão de sessões do Orca ainda não está disponível, então nenhuma mensagem foi encaminhada a um agente.";
  }

  const roots = await listProjectRoots();
  if (roots.length === 0) {
    return "Ainda não há pastas cadastradas. Abra Projetos → Gerenciar pastas para escolher quais diretórios o Jarvis pode consultar.";
  }

  const activity = await Promise.all(roots.map(async (root) => {
    try {
      return [root.id, await getGitActivity(root.id)] as const;
    } catch {
      return [root.id, undefined] as const;
    }
  }));
  const activityById = new Map<string, GitActivity | undefined>(activity);
  const hasAndamentoQuestion = /em andamento|andamento|ativo|ativos|trabalhando/i.test(question);
  const lines = roots.map((root) => {
    const git = activityById.get(root.id);
    if (!git || git.availability !== "available") return `• ${root.name}: não consegui consultar o estado Git desta pasta.`;
    const branch = git.branch ? ` · branch ${git.branch}` : "";
    if (git.changedPaths.length > 0) {
      return `• ${root.name}${branch}: ${git.changedPaths.length}${git.truncated ? "+" : ""} arquivo(s) com alterações locais${git.changedPaths.length ? ` (${git.changedPaths.slice(0, 3).join(", ")})` : ""}.`;
    }
    const latestCommit = git.recentCommits[0]?.subject;
    return `• ${root.name}${branch}: sem alterações locais rastreadas${latestCommit ? `; último commit: ${latestCommit}` : ""}.`;
  });

  const preface = hasAndamentoQuestion
    ? `Encontrei ${roots.length} pasta(s) configurada(s). Não consigo confirmar quais estão em andamento sem ler as sessões do Orca. Os sinais disponíveis no Git são:\n`
    : `Estado local de ${roots.length} pasta(s) configurada(s):\n`;
  const orcaNote = connection?.connected
    ? "\n\nO CLI do Orca responde, mas o Jarvis ainda não está lendo sessões nem encaminhando mensagens."
    : "\n\nAinda não consegui conectar ao runtime do Orca; por isso, isto não indica atividade de agentes.";
  return `${preface}${lines.join("\n")}${orcaNote}`;
}
