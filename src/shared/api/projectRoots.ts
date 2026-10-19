import { invoke } from "@tauri-apps/api/core";
import type { GitActivity } from "../types/project";
import type { ProjectRoot } from "../types/projectRoot";

export function addProjectRoot(path: string): Promise<ProjectRoot> {
  return invoke<ProjectRoot>("add_project_root", { path });
}

export function listProjectRoots(): Promise<ProjectRoot[]> {
  return invoke<ProjectRoot[]>("list_project_roots");
}

export function removeProjectRoot(projectId: string): Promise<void> {
  return invoke<void>("remove_project_root", { projectId });
}

export function getGitActivity(projectId: string): Promise<GitActivity> {
  return invoke<GitActivity>("get_git_activity", { projectId });
}
