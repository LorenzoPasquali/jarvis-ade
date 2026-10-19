import { useEffect, useRef, useState, type RefObject } from "react";
import { getAppVersion } from "../shared/api/app";
import { checkOrcaConnection } from "../shared/api/orca";
import { clearChatHistory } from "../shared/api/settings";
import { getGitActivity, listProjectRoots } from "../shared/api/projectRoots";
import { getLocalSpeechStatus, prepareLocalSpeech, speakLocalText, type LocalSpeechStatus } from "../shared/api/voice";
import type { GitActivity } from "../shared/types/project";
import type { ProjectRoot } from "../shared/types/projectRoot";
import type { OrcaConnection } from "../shared/types/orca";
import { Icon, type IconName } from "../components/Icon";
import ProjectRoots from "../features/settings/ProjectRoots";
import ProjectContextPanel from "../features/projects/ProjectContextPanel";
import CommandApprovalDialog from "../features/commands/CommandApprovalDialog";
import InboxPage from "../features/inbox/InboxPage";

type View = "projects" | "inbox" | "settings";

const routes: Record<View, { label: string; icon: IconName; eyebrow: string }> = {
  projects: { label: "Projetos", icon: "projects", eyebrow: "ESPAÇO DE TRABALHO" },
  inbox: { label: "Conversa", icon: "inbox", eyebrow: "CENTRAL DO JARVIS" },
  settings: { label: "Configurações", icon: "settings", eyebrow: "PREFERÊNCIAS LOCAIS" },
};

export default function App() {
  const [view, setView] = useState<View>("inbox");
  const [appVersion, setAppVersion] = useState<string | null>(null);
  const [orcaConnection, setOrcaConnection] = useState<OrcaConnection | null>(null);
  const [checkingOrca, setCheckingOrca] = useState(false);
  const [orcaCheckKey, setOrcaCheckKey] = useState(0);
  const [coreUnavailable, setCoreUnavailable] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [clearError, setClearError] = useState<string | null>(null);
  const clearButtonRef = useRef<HTMLButtonElement>(null);
  const cancelButtonRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);

  const page = routes[view];

  useEffect(() => {
    document.title = `${page.label} — Jarvis`;
  }, [page.label]);

  useEffect(() => {
    let mounted = true;
    getAppVersion()
      .then((version) => {
        if (mounted) {
          setAppVersion(version);
          setCoreUnavailable(false);
        }
      })
      .catch(() => {
        if (mounted) setCoreUnavailable(true);
      });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    let mounted = true;
    setCheckingOrca(true);
    checkOrcaConnection()
      .then((connection) => {
        if (mounted) setOrcaConnection(connection);
      })
      .catch(() => {
        if (mounted) {
          setOrcaConnection({
            connected: false,
            state: "connection_failed",
            message: "Não foi possível consultar o CLI do Orca. Tente novamente.",
          });
        }
      })
      .finally(() => {
        if (mounted) setCheckingOrca(false);
      });
    return () => {
      mounted = false;
    };
  }, [orcaCheckKey]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (confirmOpen && !dialog.open) {
      dialog.showModal();
      cancelButtonRef.current?.focus();
    } else if (!confirmOpen && dialog.open) {
      dialog.close();
    }
  }, [confirmOpen]);

  const closeConfirmation = () => {
    setConfirmOpen(false);
    setClearError(null);
    window.requestAnimationFrame(() => clearButtonRef.current?.focus());
  };

  const handleClearHistory = async () => {
    setIsClearing(true);
    setClearError(null);
    try {
      await clearChatHistory();
      setNotice("Histórico do Jarvis apagado.");
      setConfirmOpen(false);
      window.requestAnimationFrame(() => clearButtonRef.current?.focus());
    } catch {
      setClearError("Não foi possível apagar o histórico. Tente novamente.");
    } finally {
      setIsClearing(false);
    }
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">
            <Icon name="orbit" size={25} />
            <span />
          </div>
          <div className="brand-copy">
            <span className="brand-name">JARVIS</span>
            <span className="brand-caption">LOCAL WORKBENCH</span>
          </div>
        </div>

        <div className="nav-label">SEU ESPAÇO</div>
        <nav className="primary-nav" aria-label="Navegação principal">
          {(Object.keys(routes) as View[]).map((route) => (
            <button
              className={`nav-item${view === route ? " is-current" : ""}`}
              key={route}
              type="button"
              aria-current={view === route ? "page" : undefined}
              onClick={() => {
                setNotice(null);
                setView(route);
              }}
            >
              <span className="nav-icon"><Icon name={routes[route].icon} size={19} /></span>
              <span>{routes[route].label}</span>
              {view === route && <span className="nav-focus-spine" aria-hidden="true" />}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-footer-rule" />
          <div className="local-engine-mark"><span className="local-engine-dot" /> NÚCLEO LOCAL</div>
          <p>{coreUnavailable ? "Aguardando conexão com o app" : "Dados permanecem neste dispositivo"}</p>
          <span className="engine-version">{appVersion ? `v${appVersion}` : "Jarvis desktop"}</span>
        </div>
      </aside>

      <main className="main-column">
        <header className="topbar">
          <div className="topbar-heading">
            <span className="eyebrow">{page.eyebrow}</span>
            <h1>{page.label}</h1>
          </div>
          <div className="topbar-status">
            <button
              className={`orca-status${orcaConnection?.connected ? " is-connected" : ""}`}
              type="button"
              aria-label="Testar conexão com o Orca"
              onClick={() => setOrcaCheckKey((current) => current + 1)}
              disabled={checkingOrca}
              title={orcaConnection?.message ?? "Testar conexão com o Orca"}
            >
              <span className="status-marker" />
              <span>{checkingOrca ? "Verificando CLI do Orca" : orcaConnection?.connected ? "CLI do Orca acessível" : "CLI do Orca desconectado"}</span>
            </button>
            <div className={`core-status${coreUnavailable ? " is-error" : ""}`} aria-live="polite">
              <span className="core-status-dot" />
              {coreUnavailable ? "Núcleo local indisponível" : appVersion ? "Núcleo local ativo" : "Conectando ao núcleo"}
            </div>
          </div>
        </header>

        <div className="page-content">
          {notice && (
            <div className="notice notice-success" role="status">
              <Icon name="check" size={17} />
              <span>{notice}</span>
              <button type="button" className="icon-button" aria-label="Fechar aviso" onClick={() => setNotice(null)}>
                <Icon name="close" size={16} />
              </button>
            </div>
          )}

          {view === "projects" && (
            <ProjectsPage
              onNavigate={setView}
              connection={orcaConnection}
              checkingConnection={checkingOrca}
              onCheckConnection={() => setOrcaCheckKey((current) => current + 1)}
            />
          )}
          {view === "inbox" && (
            <InboxPage
              onNavigate={setView}
              connection={orcaConnection}
              checkingConnection={checkingOrca}
              onCheckConnection={() => setOrcaCheckKey((current) => current + 1)}
            />
          )}
          {view === "settings" && (
            <SettingsPage
              connection={orcaConnection}
              onClear={() => {
                setClearError(null);
                setConfirmOpen(true);
              }}
              clearButtonRef={clearButtonRef}
            />
          )}
        </div>
      </main>

      <dialog
        className="confirm-dialog"
        ref={dialogRef}
        aria-labelledby="clear-history-title"
        aria-describedby="clear-history-description"
        onCancel={(event) => {
          event.preventDefault();
          if (!isClearing) closeConfirmation();
        }}
      >
        <div className="dialog-icon"><Icon name="trash" size={20} /></div>
        <span className="eyebrow">AÇÃO PERMANENTE</span>
        <h2 id="clear-history-title">Apagar o histórico do Jarvis?</h2>
        <p id="clear-history-description">
          As mensagens de texto guardadas por este app serão removidas deste dispositivo. Isso não apaga conversas do Claude Code.
        </p>
        {clearError && <p className="dialog-error" role="alert">{clearError}</p>}
        <div className="dialog-actions">
          <button
            className="button button-quiet"
            ref={cancelButtonRef}
            type="button"
            disabled={isClearing}
            onClick={closeConfirmation}
          >
            Cancelar
          </button>
          <button
            className="button button-danger"
            type="button"
            disabled={isClearing}
            onClick={handleClearHistory}
          >
            {isClearing ? "Apagando…" : "Apagar histórico"}
          </button>
        </div>
      </dialog>
    </div>
  );
}

function ProjectsPage({
  onNavigate,
  connection,
  checkingConnection,
  onCheckConnection,
}: {
  onNavigate: (view: View) => void;
  connection: OrcaConnection | null;
  checkingConnection: boolean;
  onCheckConnection: () => void;
}) {
  const [roots, setRoots] = useState<ProjectRoot[]>([]);
  const [activityById, setActivityById] = useState<Record<string, GitActivity | undefined>>({});
  const [refreshingIds, setRefreshingIds] = useState<Set<string>>(() => new Set());
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    let mounted = true;
    const loadCatalog = async () => {
      try {
        const items = await listProjectRoots();
        if (!mounted) return;
        setRoots(items);
        setIsLoading(false);

        for (let offset = 0; offset < items.length; offset += 3) {
          const batch = items.slice(offset, offset + 3);
          const results = await Promise.all(
            batch.map(async (root) => {
              try {
                return [root.id, await getGitActivity(root.id)] as const;
              } catch {
                return [root.id, undefined] as const;
              }
            }),
          );
          if (mounted) {
            setActivityById((current) => ({
              ...current,
              ...Object.fromEntries(results),
            }));
          }
        }
      } catch {
        if (mounted) setLoadError(true);
      } finally {
        if (mounted) setIsLoading(false);
      }
    };
    void loadCatalog();
    return () => {
      mounted = false;
    };
  }, []);

  const refreshActivity = async (root: ProjectRoot) => {
    setRefreshingIds((current) => new Set(current).add(root.id));
    try {
      const activity = await getGitActivity(root.id);
      setActivityById((current) => ({ ...current, [root.id]: activity }));
    } catch {
      setActivityById((current) => ({ ...current, [root.id]: undefined }));
    } finally {
      setRefreshingIds((current) => {
        const next = new Set(current);
        next.delete(root.id);
        return next;
      });
    }
  };

  return (
    <>
      <section className="page-intro">
        <div>
          <h2>Um lugar para cada projeto.</h2>
          <p>Veja suas pastas locais sem misturar o contexto de cada agente.</p>
        </div>
        <span className="intro-local-label"><span className="local-engine-dot" /> EXECUÇÃO LOCAL</span>
      </section>

      <section className={`integration-card${connection?.connected ? " is-connected" : ""}`} aria-labelledby="orca-integration-title">
        <div className="integration-icon"><Icon name="orbit" size={22} /></div>
        <div className="integration-copy">
          <span className="eyebrow">SESSÕES E AGENTES</span>
          <h3 id="orca-integration-title">{connection?.connected ? "CLI do Orca respondeu; sessões pendentes" : "Sessões do Orca ainda não conectadas"}</h3>
          <p>{connection?.message ?? "O Jarvis ainda não verificou a conexão. As pastas adicionadas manualmente já podem formar o catálogo local."}</p>
        </div>
        <button className="integration-state integration-retry" type="button" onClick={onCheckConnection} disabled={checkingConnection}>
          <span className="status-marker" /> {checkingConnection ? "VERIFICANDO" : connection?.connected ? "VERIFICAR NOVAMENTE" : "TESTAR CONEXÃO"}
        </button>
      </section>

      <section className="project-catalog" aria-labelledby="project-catalog-title">
        <div className="project-catalog-heading">
          <div>
            <span className="eyebrow">CATÁLOGO LOCAL</span>
            <h3 id="project-catalog-title">Pastas de projetos</h3>
          </div>
          <button className="button button-secondary" type="button" onClick={() => onNavigate("settings")}>
            <Icon name="folder" size={17} /> Gerenciar pastas
          </button>
        </div>

        {isLoading ? (
          <div className="project-catalog-empty" role="status">Carregando projetos…</div>
        ) : loadError ? (
          <div className="project-catalog-empty is-error" role="alert">Não foi possível carregar as pastas locais.</div>
        ) : roots.length === 0 ? (
          <div className="project-catalog-empty">
            <div className="empty-symbol"><Icon name="folder" size={26} /></div>
            <h4>Nenhuma pasta adicionada</h4>
            <p>Escolha as pastas que o Jarvis poderá consultar. Não há varredura automática do disco.</p>
            <button className="button button-secondary" type="button" onClick={() => onNavigate("settings")}>
              Adicionar pasta <Icon name="arrow-right" size={17} />
            </button>
          </div>
        ) : (
          <ul className="project-catalog-list">
            {roots.map((root) => {
              const activity = activityById[root.id];
              return (
                <li className="project-catalog-item" key={root.id}>
                  <div className="settings-row-icon"><Icon name="folder" size={19} /></div>
                  <div className="project-catalog-copy">
                    <h4>{root.name}</h4>
                    <code title={root.path}>{root.path}</code>
                  </div>
                  <ProjectGitStatus
                    activity={activity}
                    isRefreshing={refreshingIds.has(root.id)}
                    onRefresh={() => void refreshActivity(root)}
                  />
                  <ProjectContextPanel
                    projectId={root.id}
                    suggestedPaths={activity?.availability === "available" ? activity.changedPaths.slice(0, 5) : []}
                  />
                  <CommandApprovalDialog projectId={root.id} projectName={root.name} />
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <footer className="page-footnote">
        <span className="footnote-rule" />
        <span>Pastas canônicas escolhidas por você. A leitura dos arquivos ainda não está ativa.</span>
      </footer>
    </>
  );
}

function ProjectGitStatus({
  activity,
  isRefreshing,
  onRefresh,
}: {
  activity: GitActivity | undefined;
  isRefreshing: boolean;
  onRefresh: () => void;
}) {
  let stateLabel = "Consultando Git…";
  if (activity) {
    switch (activity.availability) {
      case "available":
        stateLabel = activity.clean === true
          ? "Sem alterações rastreadas"
          : `${activity.changedPaths.length}${activity.truncated ? "+" : ""} alterações rastreadas`;
        break;
      case "not_repository":
        stateLabel = "Esta pasta não é um repositório Git";
        break;
      case "root_outside_configured_folder":
        stateLabel = "O repositório Git fica acima desta pasta";
        break;
      case "unavailable":
        stateLabel = "Git indisponível nesta pasta";
        break;
    }
  }

  return (
    <div className="project-git-details" aria-live="polite">
      <span className="project-git-state">
        {activity?.availability === "available" && activity.branch ? `Branch ${activity.branch} · ` : ""}
        {stateLabel}
      </span>
      {activity?.availability === "available" && activity.recentCommits[0] && (
        <span className="project-git-commit" title={activity.recentCommits[0].subject}>
          Último commit: {activity.recentCommits[0].shortHash} · {activity.recentCommits[0].subject}
        </span>
      )}
      {activity?.availability === "available" && activity.diffSummary && (
        <span className="project-git-commit">Diff: {activity.diffSummary}</span>
      )}
      {activity?.availability === "available" && activity.changedPaths.length > 0 && (
        <span className="project-git-paths" title={activity.changedPaths.join("\n")}>
          {activity.changedPaths.slice(0, 3).join(" · ")}
          {activity.changedPaths.length > 3 && ` · +${activity.changedPaths.length - 3}`}
        </span>
      )}
      <button className="project-refresh-button" type="button" onClick={onRefresh} disabled={isRefreshing}>
        {isRefreshing ? "Atualizando…" : "Atualizar"}
      </button>
    </div>
  );
}

function SettingsPage({
  onClear,
  clearButtonRef,
  connection,
}: {
  onClear: () => void;
  clearButtonRef: RefObject<HTMLButtonElement | null>;
  connection: OrcaConnection | null;
}) {
  const [speechStatus, setSpeechStatus] = useState<LocalSpeechStatus | null>(null);
  const [hfToken, setHfToken] = useState("");
  const [isPreparingSpeech, setIsPreparingSpeech] = useState(false);
  const [isTestingSpeech, setIsTestingSpeech] = useState(false);
  const [hasAttemptedPrepare, setHasAttemptedPrepare] = useState(false);
  const [speechFeedback, setSpeechFeedback] = useState<string | null>(null);
  const [speechFeedbackIsError, setSpeechFeedbackIsError] = useState(false);
  const testAudioRef = useRef<HTMLAudioElement | null>(null);
  const testAudioUrlRef = useRef<string | null>(null);

  useEffect(() => {
    let mounted = true;
    void getLocalSpeechStatus()
      .then((status) => {
        if (mounted) setSpeechStatus(status);
      })
      .catch(() => {
        if (mounted) setSpeechFeedback("Não consegui consultar a voz local agora.");
      });
    return () => {
      mounted = false;
      testAudioRef.current?.pause();
      if (testAudioUrlRef.current) URL.revokeObjectURL(testAudioUrlRef.current);
    };
  }, []);

  const handlePrepareSpeech = async () => {
    setHasAttemptedPrepare(true);
    setIsPreparingSpeech(true);
    setSpeechFeedback(null);
    setSpeechStatus({
      ready: false,
      message: "Instalando o Pocket TTS e baixando os pesos uma vez. Isso pode levar alguns minutos.",
    });
    try {
      const status = await prepareLocalSpeech(hfToken.trim() || undefined);
      setSpeechStatus(status);
      if (status.ready) setHfToken("");
    } catch (error) {
      const message = error && typeof error === "object" && "message" in error && typeof error.message === "string"
        ? error.message
        : "Não consegui preparar a voz local. Confira Python 3 e a conexão para o primeiro download.";
      setSpeechStatus({ ready: false, message });
    } finally {
      setHfToken("");
      setIsPreparingSpeech(false);
    }
  };

  const handleTestSpeech = async () => {
    setIsTestingSpeech(true);
    setSpeechFeedback(null);
    testAudioRef.current?.pause();
    if (testAudioUrlRef.current) URL.revokeObjectURL(testAudioUrlRef.current);
    try {
      const bytes = await speakLocalText("Olá, senhor. Eu sou o Jarvis. Estou falando com a minha voz local.");
      const url = URL.createObjectURL(new Blob([new Uint8Array(bytes)], { type: "audio/wav" }));
      const audio = new Audio(url);
      testAudioRef.current = audio;
      testAudioUrlRef.current = url;
      audio.onended = () => {
        if (testAudioRef.current !== audio) return;
        testAudioRef.current = null;
        testAudioUrlRef.current = null;
        URL.revokeObjectURL(url);
      };
      audio.onerror = () => {
        setSpeechFeedback("O áudio foi gerado, mas não consegui reproduzi-lo neste dispositivo.");
        setSpeechFeedbackIsError(true);
      };
      await audio.play();
      setSpeechFeedback("Teste de voz iniciado no dispositivo.");
      setSpeechFeedbackIsError(false);
    } catch (error) {
      const message = error && typeof error === "object" && "message" in error && typeof error.message === "string"
        ? error.message
        : "Não consegui gerar o áudio de teste.";
      setSpeechFeedback(message);
      setSpeechFeedbackIsError(true);
    } finally {
      setIsTestingSpeech(false);
    }
  };

  return (
    <>
      <section className="page-intro">
        <div>
          <h2>Preferências deste dispositivo.</h2>
          <p>Histórico e configurações do Jarvis ficam localmente.</p>
        </div>
      </section>

      <section className="settings-group" aria-labelledby="local-data-title">
        <div className="settings-group-heading">
          <span className="eyebrow">PRIVACIDADE LOCAL</span>
          <h3 id="local-data-title">Dados do Jarvis</h3>
        </div>
        <div className="settings-row">
          <div className="settings-row-icon"><Icon name="message" size={19} /></div>
          <div className="settings-row-copy">
            <h4>Histórico de texto</h4>
            <p>As mensagens do Jarvis são guardadas neste dispositivo. Áudio bruto e histórico completo de terminal não são armazenados.</p>
          </div>
          <button className="button button-danger-outline" ref={clearButtonRef} type="button" onClick={onClear}>
            <Icon name="trash" size={16} /> Limpar histórico
          </button>
        </div>
      </section>

      <section className="settings-group" aria-labelledby="local-voice-title">
        <div className="settings-group-heading">
          <span className="eyebrow">VOZ LOCAL</span>
          <h3 id="local-voice-title">Faça o Jarvis falar.</h3>
        </div>
        <div className="settings-row">
          <div className="settings-row-icon"><Icon name="speaker" size={19} /></div>
          <div className="settings-row-copy">
            <h4>{speechStatus?.ready ? "Voz Jarvis preparada" : "Prepare a voz uma vez"}</h4>
            <p>
              A primeira preparação baixa o modelo de voz. Os pesos de clonagem exigem acesso aprovado na Hugging Face; depois, as respostas são geradas offline usando o MP3 Jarvis como referência.
            </p>
            {!speechStatus?.ready && (
              <div className="voice-token-field">
                <label htmlFor="huggingface-token">Token de leitura da Hugging Face</label>
                <input
                  id="huggingface-token"
                  type="password"
                  autoComplete="off"
                  spellCheck={false}
                  value={hfToken}
                  onChange={(event) => setHfToken(event.currentTarget.value)}
                  disabled={isPreparingSpeech}
                  placeholder="hf_…"
                  aria-describedby="huggingface-token-help"
                />
                <span id="huggingface-token-help">
                  Aceite as condições em huggingface.co/kyutai/pocket-tts e cole aqui seu token de leitura. Ele é necessário no primeiro download, só é usado nesta preparação e não é salvo pelo Jarvis.
                </span>
              </div>
            )}
            {hasAttemptedPrepare && speechStatus?.message && (
              <p className={`speech-feedback${!speechStatus.ready && !isPreparingSpeech ? " is-error" : ""}`} role="status">
                {speechStatus.message}
              </p>
            )}
            {speechFeedback && <p className={`speech-feedback${speechFeedbackIsError ? " is-error" : ""}`} role="status">{speechFeedback}</p>}
          </div>
          <div className="speech-actions">
            <button className="button button-primary" type="button" onClick={() => void handlePrepareSpeech()} disabled={isPreparingSpeech || speechStatus === null || speechStatus.ready}>
              {isPreparingSpeech ? "Preparando voz…" : speechStatus?.ready ? "Voz pronta" : "Preparar voz Jarvis"}
            </button>
            {speechStatus?.ready && (
              <button className="button button-secondary" type="button" onClick={() => void handleTestSpeech()} disabled={isTestingSpeech}>
                <Icon name="speaker" size={16} /> {isTestingSpeech ? "Gerando teste…" : "Testar voz"}
              </button>
            )}
          </div>
        </div>
      </section>

      <ProjectRoots />

      <section className="settings-group settings-coming-soon" aria-labelledby="integrations-title">
        <div className="settings-group-heading">
          <span className="eyebrow">EM PREPARAÇÃO</span>
          <h3 id="integrations-title">Integrações</h3>
        </div>
        <div className="integration-list-row">
          <span className="integration-list-mark">O</span>
          <span>Orca</span>
          <span className="integration-list-state"><span className="status-marker" /> {connection?.connected ? "CLI acessível; sessões pendentes" : "CLI não conectado"}</span>
        </div>
        <div className="integration-list-row">
          <span className="integration-list-mark voice-mark">V</span>
          <span>Voz local</span>
          <span className="integration-list-state"><span className="status-marker" /> {speechStatus?.ready ? "Pocket TTS · português · offline" : "Preparação necessária"}</span>
        </div>
      </section>
    </>
  );
}
