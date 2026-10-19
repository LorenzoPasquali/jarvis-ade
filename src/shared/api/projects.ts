import { invoke } from "@tauri-apps/api/core";
import type { ProjectSummary } from "../types/project";
import type { SessionSummary } from "../types/session";

export function saveProjectSummary(project: ProjectSummary): Promise<void> {
  return invoke<void>("save_project_summary", { project });
}

export function saveSessionSummary(session: SessionSummary): Promise<void> {
  return invoke<void>("save_session_summary", { session });
}
