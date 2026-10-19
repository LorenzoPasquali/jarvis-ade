import { invoke } from "@tauri-apps/api/core";

export function getPreference(key: string): Promise<string | null> {
  return invoke<string | null>("get_preference", { key });
}

export function setPreference(key: string, value: string, updatedAt: string): Promise<void> {
  return invoke<void>("set_preference", { key, value, updatedAt });
}
