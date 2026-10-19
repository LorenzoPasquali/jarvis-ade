import { invoke } from "@tauri-apps/api/core";
import type { ChatMessage, ChatMessageRole } from "../types/inbox";

export function saveChatMessage(
  role: ChatMessageRole,
  body: string,
  createdAt: string,
): Promise<ChatMessage> {
  return invoke<ChatMessage>("save_chat_message", { role, body, createdAt });
}

export function listChatMessages(limit = 100): Promise<ChatMessage[]> {
  return invoke<ChatMessage[]>("list_chat_messages", { limit });
}

export function clearChatHistory(): Promise<void> {
  return invoke<void>("clear_chat_history");
}
