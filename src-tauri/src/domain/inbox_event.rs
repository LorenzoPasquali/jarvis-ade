use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum InboxEventKind {
    Output,
    Approval,
    UserMessage,
    AssistantMessage,
    StateChanged,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct InboxEvent {
    pub id: String,
    pub session_id: String,
    pub kind: InboxEventKind,
    pub text: String,
    pub created_at: String,
}
