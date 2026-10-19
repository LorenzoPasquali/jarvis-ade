import { useState, type FormEvent } from "react";
import { Icon } from "../../components/Icon";
import { readProjectFile, searchProject } from "../../shared/api/projectFiles";
import type { FileExcerpt } from "../../shared/types/project";

function errorMessage(error: unknown): string {
  if (typeof error === "object" && error !== null && "message" in error) {
    const message = (error as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  return "Não foi possível consultar os arquivos desta pasta.";
}

export default function ProjectContextPanel({
  projectId,
  suggestedPaths,
}: {
  projectId: string;
  suggestedPaths: string[];
}) {
  const [relativePath, setRelativePath] = useState("README.md");
  const [query, setQuery] = useState("");
  const [excerpts, setExcerpts] = useState<FileExcerpt[]>([]);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  const readPath = async (path: string) => {
    setRelativePath(path);
    setIsBusy(true);
    setError(null);
    setHasSearched(false);
    try {
      setExcerpts([await readProjectFile(projectId, path)]);
    } catch (readError) {
      setExcerpts([]);
      setError(errorMessage(readError));
    } finally {
      setIsBusy(false);
    }
  };

  const handleRead = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await readPath(relativePath);
  };

  const handleSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsBusy(true);
    setError(null);
    setHasSearched(true);
    try {
      setExcerpts(await searchProject(projectId, query, 8));
    } catch (searchError) {
      setExcerpts([]);
      setError(errorMessage(searchError));
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <details className="project-context-details">
      <summary><Icon name="search" size={16} /> Consultar arquivos desta pasta</summary>
      <div className="project-context-body">
        <div className="project-context-shortcuts">
          <span>Atalhos locais</span>
          {[...new Set(["AGENTS.md", "README.md", ...suggestedPaths])].slice(0, 7).map((path) => (
            <button key={path} type="button" onClick={() => void readPath(path)} disabled={isBusy}>
              {path}
            </button>
          ))}
        </div>

        <form className="project-context-form" noValidate onSubmit={handleRead}>
          <label htmlFor={`read-path-${projectId}`}>Ler arquivo por caminho relativo</label>
          <div className="project-context-input-row">
            <input
              id={`read-path-${projectId}`}
              value={relativePath}
              onChange={(event) => setRelativePath(event.target.value)}
              placeholder="README.md"
              autoComplete="off"
            />
            <button className="button button-quiet" type="submit" disabled={isBusy || !relativePath.trim()}>
              {isBusy ? "Consultando…" : "Ler arquivo"}
            </button>
          </div>
        </form>

        <form className="project-context-form" noValidate onSubmit={handleSearch}>
          <label htmlFor={`search-query-${projectId}`}>Buscar texto nos arquivos</label>
          <div className="project-context-input-row">
            <input
              id={`search-query-${projectId}`}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Ex.: TODO, nome de função…"
              autoComplete="off"
            />
            <button className="button button-secondary" type="submit" disabled={isBusy || !query.trim()}>
              {isBusy ? "Buscando…" : "Buscar"}
            </button>
          </div>
        </form>

        <p className="project-context-privacy">
          Trechos locais com limite de tamanho. Resultados não são enviados a nenhum agente.
        </p>

        {error && <p className="project-context-error" role="alert">{error}</p>}
        {hasSearched && excerpts.length === 0 && !error && (
          <p className="project-context-empty" role="status">Nenhuma correspondência encontrada.</p>
        )}
        {excerpts.length > 0 && (
          <ul className="project-context-results" aria-label="Trechos locais encontrados">
            {excerpts.map((excerpt, index) => (
              <li key={`${excerpt.relativePath}:${excerpt.startLine}:${index}`}>
                <div className="project-context-source">
                  <code>{excerpt.relativePath}:{excerpt.startLine}</code>
                  <button
                    type="button"
                    className="project-context-read-source"
                    onClick={() => setRelativePath(excerpt.relativePath)}
                  >
                    Usar caminho
                  </button>
                </div>
                <pre>{excerpt.text}</pre>
              </li>
            ))}
          </ul>
        )}
      </div>
    </details>
  );
}
