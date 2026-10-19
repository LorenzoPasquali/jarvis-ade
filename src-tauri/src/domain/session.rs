use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SessionState {
    Working,
    NeedsReply,
    Completed,
    Unknown,
}

impl SessionState {
    pub fn as_database_value(self) -> &'static str {
        match self {
            Self::Working => "working",
            Self::NeedsReply => "needs_reply",
            Self::Completed => "completed",
            Self::Unknown => "unknown",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SessionSummary {
    pub id: String,
    pub project_id: String,
    pub terminal_id: Option<String>,
    pub claude_session_id: Option<String>,
    pub agent: String,
    pub state: SessionState,
    pub last_seen_at: Option<String>,
}
