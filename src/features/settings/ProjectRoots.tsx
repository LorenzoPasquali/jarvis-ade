import { useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { Icon } from "../../components/Icon";
import { addProjectRoot, listProjectRoots, removeProjectRoot } from "../../shared/api/projectRoots";
import type { ProjectRoot } from "../../shared/types/projectRoot";

function publicError(error: unknown, fallback: string): string {
  if (typeof error === "object" && error !== null && "message" in error) {
    const message = (error as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  return fallback;
}

export default function ProjectRoots() {
  const [roots, setRoots] = useState<ProjectRoot[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isBusy, setIsBusy] = useState(false);
  const [pendingRemoval, setPendingRemoval] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ kind: "status" | "error"; text: string } | null>(null);

  const refreshRoots = async () => {
    setIsLoading(true);
    try {
      setRoots(await listProjectRoots());
    } catch {
      setFeedback({ kind: "error", text: "Não foi possível carregar as pastas locais." });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void refreshRoots();
  }, []);

  const handleAdd = async () => {
    setFeedback(null);
    setIsBusy(true);
    try {
      const selectedPath = await open({
        title: "Escolher pasta de projeto",
        directory: true,
        multiple: false,
      });
      if (!selectedPath) return;

      const added = await addProjectRoot(selectedPath);
      setRoots((current) => [...current, added].sort((a, b) => a.name.localeCompare(b.name)));
      setFeedback({ kind: "status", text: `A pasta ${added.name} foi adicionada ao Jarvis.` });
    } catch (error) {
      setFeedback({
        kind: "error",
        text: publicError(error, "Não foi possível adicionar essa pasta."),
      });
    } finally {
      setIsBusy(false);
    }
  };

  const handleRemove = async (root: ProjectRoot) => {
    setIsBusy(true);
    setFeedback(null);
    try {
      await removeProjectRoot(root.id);
      setRoots((current) => current.filter((item) => item.id !== root.id));
      setPendingRemoval(null);
      setFeedback({
        kind: "status",
        text: `${root.name} saiu do catálogo local. Os arquivos e as sessões do Orca não foram alterados.`,
      });
    } catch (error) {
      setFeedback({
        kind: "error",
        text: publicError(error, "Não foi possível remover essa pasta do Jarvis."),
      });
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <section className="settings-group project-roots" aria-labelledby="project-roots-title">
      <div className="settings-group-heading project-roots-heading">
        <div>
          <span className="eyebrow">ACESSO LOCAL EXPLÍCITO</span>
          <h3 id="project-roots-title">Pastas de projetos</h3>
        </div>
        <button className="button button-secondary" type="button" onClick={handleAdd} disabled={isBusy}>
          <Icon name="folder" size={17} />
          {isBusy ? "Aguarde…" : "Escolher pasta"}
        </button>
      </div>

      <p className="project-roots-description">
        O Jarvis só consultará as pastas que você adicionar aqui. Remover uma pasta apaga apenas o vínculo local.
      </p>

      {feedback && (
        <p className={`project-roots-feedback is-${feedback.kind}`} role={feedback.kind === "error" ? "alert" : "status"}>
          {feedback.text}
        </p>
      )}

      {isLoading ? (
        <p className="project-roots-empty" role="status">Carregando pastas…</p>
      ) : roots.length === 0 ? (
        <p className="project-roots-empty">Nenhuma pasta adicionada. O disco não é varrido automaticamente.</p>
      ) : (
        <ul className="project-root-list">
          {roots.map((root) => (
            <li className="project-root-item" key={root.id}>
              <div className="settings-row-icon"><Icon name="folder" size={18} /></div>
              <div className="project-root-copy">
                <strong>{root.name}</strong>
                <code title={root.path}>{root.path}</code>
              </div>
              {pendingRemoval === root.id ? (
                <div className="project-root-confirm">
                  <span>Remover só do Jarvis?</span>
                  <button className="button button-quiet" type="button" onClick={() => setPendingRemoval(null)} disabled={isBusy}>
                    Manter
                  </button>
                  <button className="button button-danger" type="button" onClick={() => void handleRemove(root)} disabled={isBusy}>
                    Remover
                  </button>
                </div>
              ) : (
                <button
                  className="button button-danger-outline"
                  type="button"
                  aria-label={`Remover ${root.name} da lista do Jarvis`}
                  onClick={() => setPendingRemoval(root.id)}
                  disabled={isBusy}
                >
                  Remover
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
