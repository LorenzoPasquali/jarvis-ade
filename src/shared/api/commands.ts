import { invoke } from "@tauri-apps/api/core";
import type { CommandPreview, CommandResult, CommandRequest } from "../types/project";

export function previewCommand(request: CommandRequest): Promise<CommandPreview> {
  return invoke<CommandPreview>("preview_command", { request });
}

export function runConfirmedCommand(confirmationId: string): Promise<CommandResult> {
  return invoke<CommandResult>("run_confirmed_command", { confirmationId });
}
