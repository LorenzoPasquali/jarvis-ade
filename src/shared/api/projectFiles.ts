import { invoke } from "@tauri-apps/api/core";
import type { FileExcerpt } from "../types/project";

export function readProjectFile(projectId: string, relativePath: string): Promise<FileExcerpt> {
  return invoke<FileExcerpt>("read_project_file", { projectId, relativePath });
}

export function searchProject(projectId: string, query: string, limit = 8): Promise<FileExcerpt[]> {
  return invoke<FileExcerpt[]>("search_project", { projectId, query, limit });
}
