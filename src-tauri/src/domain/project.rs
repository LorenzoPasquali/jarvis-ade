use serde::{Deserialize, Serialize};
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProjectRoot {
    pub id: String,
    pub name: String,
    pub path: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum GitAvailability {
    Available,
    NotRepository,
    RootOutsideConfiguredFolder,
    Unavailable,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RecentCommit {
    pub short_hash: String,
    pub subject: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FileExcerpt {
    pub relative_path: String,
    pub start_line: u32,
    pub text: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct GitActivity {
    pub availability: GitAvailability,
    pub branch: Option<String>,
    pub changed_paths: Vec<String>,
    pub recent_commits: Vec<RecentCommit>,
    pub diff_summary: Option<String>,
    pub clean: Option<bool>,
    pub truncated: bool,
    pub observed_at_unix_ms: u64,
}

impl GitActivity {
    pub fn unavailable(availability: GitAvailability) -> Self {
        let observed_at_unix_ms = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|duration| duration.as_millis().min(u128::from(u64::MAX)) as u64)
            .unwrap_or_default();
        Self {
            availability,
            branch: None,
            changed_paths: Vec::new(),
            recent_commits: Vec::new(),
            diff_summary: None,
            clean: None,
            truncated: false,
            observed_at_unix_ms,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProjectSummary {
    pub id: String,
    pub name: String,
    pub repo_path: String,
    pub worktree_path: Option<String>,
    pub branch: Option<String>,
    pub git_state: GitState,
    pub activity: ActivityEvidence,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct GitState {
    pub clean: bool,
    pub changed_file_count: u32,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ActivityState {
    WorkingNow,
    NeedsReply,
    Recent,
    Inactive,
    Unknown,
}

impl ActivityState {
    pub fn as_database_value(self) -> &'static str {
        match self {
            Self::WorkingNow => "working_now",
            Self::NeedsReply => "needs_reply",
            Self::Recent => "recent",
            Self::Inactive => "inactive",
            Self::Unknown => "unknown",
        }
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ActivitySource {
    Orca,
    Git,
    Manual,
    Unknown,
}

impl ActivitySource {
    pub fn as_database_value(self) -> &'static str {
        match self {
            Self::Orca => "orca",
            Self::Git => "git",
            Self::Manual => "manual",
            Self::Unknown => "unknown",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ActivityEvidence {
    pub state: ActivityState,
    pub source: ActivitySource,
    pub observed_at: Option<String>,
}
