export type SessionState = "working" | "needs_reply" | "completed" | "unknown";

export interface SessionSummary {
  id: string;
  projectId: string;
  terminalId: string | null;
  claudeSessionId: string | null;
  agent: string;
  state: SessionState;
  lastSeenAt: string | null;
}
