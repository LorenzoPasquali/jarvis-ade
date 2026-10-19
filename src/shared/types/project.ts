export type ActivityState =
  | "working_now"
  | "needs_reply"
  | "recent"
  | "inactive"
  | "unknown";

export type ActivitySource = "orca" | "git" | "manual" | "unknown";

export interface GitState {
  clean: boolean;
  changedFileCount: number;
}

export interface ActivityEvidence {
  state: ActivityState;
  source: ActivitySource;
  observedAt: string | null;
}

export interface ProjectSummary {
  id: string;
  name: string;
  repoPath: string;
  worktreePath: string | null;
  branch: string | null;
  gitState: GitState;
  activity: ActivityEvidence;
}

export type GitAvailability =
  | "available"
  | "not_repository"
  | "root_outside_configured_folder"
  | "unavailable";

export interface RecentCommit {
  shortHash: string;
  subject: string;
}

export interface GitActivity {
  availability: GitAvailability;
  branch: string | null;
  changedPaths: string[];
  recentCommits: RecentCommit[];
  diffSummary: string | null;
  clean: boolean | null;
  truncated: boolean;
  observedAtUnixMs: number;
}

export interface FileExcerpt {
  relativePath: string;
  startLine: number;
  text: string;
}

export interface CommandRequest {
  projectId: string;
  commandLine: string;
}

export interface CommandPreview {
  confirmationId: string;
  projectId: string;
  program: string;
  args: string[];
  workingDirectory: string;
  expiresAtUnixMs: number;
}

export interface CommandResult {
  exitCode: number | null;
  stdoutExcerpt: string;
  stderrExcerpt: string;
  truncated: boolean;
  timedOut: boolean;
}
