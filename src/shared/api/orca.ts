import { invoke } from "@tauri-apps/api/core";
import type { OrcaConnection } from "../types/orca";

export function checkOrcaConnection(): Promise<OrcaConnection> {
  return invoke<OrcaConnection>("check_orca_connection");
}
