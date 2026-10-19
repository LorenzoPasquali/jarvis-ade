import { useEffect, useRef, useState, type FormEvent } from "react";
import { Icon } from "../../components/Icon";
import { previewCommand, runConfirmedCommand } from "../../shared/api/commands";
import type { CommandPreview, CommandResult } from "../../shared/types/project";
import CommandOutput from "./CommandOutput";

function errorMessage(error: unknown): string {
  if (typeof error === "object" && error !== null && "message" in error) {
    const message = (error as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  return "Não foi possível preparar esse comando.";
}

export default function CommandApprovalDialog({
  projectId,
  projectName,
}: {
  projectId: string;
  projectName: string;
}) {
  const [commandLine, setCommandLine] = useState("");
  const [preview, setPreview] = useState<CommandPreview | null>(null);
  const [result, setResult] = useState<CommandResult | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const composerRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (preview && !dialog.open) {
      dialog.showModal();
      cancelRef.current?.focus();
    } else if (!preview && dialog.open) {
      dialog.close();
    }
  }, [preview]);

  const handlePreview = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsBusy(true);
    setError(null);
    setResult(null);
    try {
      setPreview(await previewCommand({ projectId, commandLine }));
    } catch (previewError) {
      setError(errorMessage(previewError));
    } finally {
      setIsBusy(false);
    }
  };

  const closePreview = () => {
    if (isBusy) return;
    setPreview(null);
    setError(null);
    window.requestAnimationFrame(() => composerRef.current?.focus());
  };

  const handleConfirm = async () => {
    if (!preview || isBusy) return;
    setIsBusy(true);
    setError(null);
    try {
      const commandResult = await runConfirmedCommand(preview.confirmationId);
      setResult(commandResult);
      setPreview(null);
    } catch (runError) {
      setError(errorMessage(runError));
      setPreview(null);
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <>
      <details className="project-command-details">
        <summary><Icon name="terminal" size={16} /> Executar comando nesta pasta</summary>
        <form className="command-composer" noValidate onSubmit={handlePreview}>
          <label htmlFor={`command-${projectId}`}>Programa e argumentos</label>
          <div className="command-composer-row">
            <input
              id={`command-${projectId}`}
              ref={composerRef}
              value={commandLine}
              onChange={(event) => setCommandLine(event.target.value)}
              placeholder="Ex.: git status --short"
              autoComplete="off"
              spellCheck={false}
            />
            <button className="button button-secondary" type="submit" disabled={isBusy || !commandLine.trim()}>
              {isBusy ? "Preparando…" : "Revisar"}
            </button>
          </div>
          <p>Sem pipe, redirecionamento ou expansão de shell. Revisar só mostra programa e argumentos; a execução exige sua confirmação.</p>
          {error && !preview && <span className="command-composer-error" role="alert">{error}</span>}
        </form>
        {result && <CommandOutput result={result} />}
      </details>

      <dialog
        className="confirm-dialog command-approval-dialog"
        ref={dialogRef}
        aria-labelledby={`command-preview-title-${projectId}`}
        aria-describedby={`command-preview-description-${projectId}`}
        onCancel={(event) => {
          event.preventDefault();
          closePreview();
        }}
      >
        <div className="dialog-icon command-dialog-icon"><Icon name="terminal" size={20} /></div>
        <span className="eyebrow">CONFIRMAÇÃO EXPLÍCITA</span>
        <h2 id={`command-preview-title-${projectId}`}>Executar este comando?</h2>
        <p id={`command-preview-description-${projectId}`}>
          Projeto: {projectName}. Confira programa, argumentos e pasta. O comando terá até 120 segundos e a saída ficará apenas nesta tela.
        </p>

        {preview && (
          <div className="command-preview-data">
            <div>
              <span>PROGRAMA</span>
              <code>{preview.program}</code>
            </div>
            <div>
              <span>ARGUMENTOS ({preview.args.length})</span>
              {preview.args.length === 0 ? <code>(nenhum)</code> : (
                <ol>
                  {preview.args.map((argument, index) => <li key={`${index}-${argument}`}><code>{argument}</code></li>)}
                </ol>
              )}
            </div>
            <div>
              <span>PASTA DO PROJETO</span>
              <code>{preview.workingDirectory}</code>
            </div>
          </div>
        )}

        {error && <p className="dialog-error" role="alert">{error}</p>}
        <div className="dialog-actions">
          <button
            className="button button-quiet"
            ref={cancelRef}
            type="button"
            disabled={isBusy}
            onClick={closePreview}
          >
            Cancelar
          </button>
          <button className="button button-danger" type="button" disabled={isBusy || !preview} onClick={() => void handleConfirm()}>
            {isBusy ? "Executando…" : "Executar este comando"}
          </button>
        </div>
      </dialog>
    </>
  );
}
