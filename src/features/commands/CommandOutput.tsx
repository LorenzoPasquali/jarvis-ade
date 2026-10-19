import type { CommandResult } from "../../shared/types/project";

export default function CommandOutput({ result }: { result: CommandResult }) {
  const state = result.timedOut
    ? "Tempo limite de 120 segundos atingido"
    : result.exitCode === 0
      ? "Comando concluído"
      : `Comando terminou com código ${result.exitCode ?? "desconhecido"}`;

  return (
    <section className={`command-output${result.exitCode === 0 && !result.timedOut ? " is-success" : " is-error"}`} aria-live="polite">
      <div className="command-output-heading">
        <strong>{state}</strong>
        {result.truncated && <span>Saída limitada a 16 KiB por canal</span>}
      </div>
      {result.stdoutExcerpt && (
        <div className="command-output-channel">
          <span>stdout</span>
          <pre>{result.stdoutExcerpt}</pre>
        </div>
      )}
      {result.stderrExcerpt && (
        <div className="command-output-channel">
          <span>stderr</span>
          <pre>{result.stderrExcerpt}</pre>
        </div>
      )}
      {!result.stdoutExcerpt && !result.stderrExcerpt && <pre>(sem saída)</pre>}
    </section>
  );
}
