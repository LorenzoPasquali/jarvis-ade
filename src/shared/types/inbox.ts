export type InboxEventKind =
  | "output"
  | "approval"
  | "user_message"
  | "assistant_message"
  | "state_changed";

export interface InboxEvent {
  id: string;
  sessionId: string;
  kind: InboxEventKind;
  text: string;
  createdAt: string;
}

export type ChatMessageRole = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: ChatMessageRole;
  body: string;
  createdAt: string;
}

export interface AppError {
  code: string;
  message: string;
}
