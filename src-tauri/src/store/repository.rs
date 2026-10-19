use std::path::Path;
use std::sync::Mutex;

use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use super::migrations;
use crate::domain::project::{ProjectRoot, ProjectSummary};
use crate::domain::session::SessionSummary;
use crate::error::AppError;

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ChatMessageRole {
    User,
    Assistant,
}

impl ChatMessageRole {
    fn as_database_value(self) -> &'static str {
        match self {
            Self::User => "user",
            Self::Assistant => "assistant",
        }
    }

    fn from_database_value(value: &str) -> Result<Self, AppError> {
        match value {
            "user" => Ok(Self::User),
            "assistant" => Ok(Self::Assistant),
            _ => Err(AppError::OperationFailed),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ChatMessage {
    pub id: String,
    pub role: ChatMessageRole,
    pub body: String,
    pub created_at: String,
}

pub struct Store {
    connection: Mutex<Connection>,
}

impl Store {
    pub fn open(path: &Path) -> Result<Self, AppError> {
        let mut connection = Connection::open(path).map_err(|_| AppError::OperationFailed)?;
        connection
            .pragma_update(None, "foreign_keys", "ON")
            .map_err(|_| AppError::OperationFailed)?;
        migrations::migrate(&mut connection)?;

        Ok(Self {
            connection: Mutex::new(connection),
        })
    }

    pub fn save_chat_message(
        &self,
        role: ChatMessageRole,
        body: String,
        created_at: String,
    ) -> Result<ChatMessage, AppError> {
        let id = Uuid::new_v4().to_string();
        let connection = self
            .connection
            .lock()
            .map_err(|_| AppError::OperationFailed)?;
        connection
            .execute(
                "INSERT INTO chat_messages (id, role, body, created_at) VALUES (?1, ?2, ?3, ?4)",
                params![id, role.as_database_value(), body, created_at],
            )
            .map_err(|_| AppError::OperationFailed)?;

        Ok(ChatMessage {
            id,
            role,
            body,
            created_at,
        })
    }

    pub fn list_chat_messages(&self, limit: u32) -> Result<Vec<ChatMessage>, AppError> {
        let bounded_limit = i64::from(limit.clamp(1, 500));
        let connection = self
            .connection
            .lock()
            .map_err(|_| AppError::OperationFailed)?;
        let mut statement = connection
            .prepare(
                "SELECT id, role, body, created_at FROM chat_messages ORDER BY created_at DESC LIMIT ?1",
            )
            .map_err(|_| AppError::OperationFailed)?;

        let rows = statement
            .query_map([bounded_limit], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, String>(3)?,
                ))
            })
            .map_err(|_| AppError::OperationFailed)?;

        let mut messages = Vec::new();
        for row in rows {
            let (id, role, body, created_at) = row.map_err(|_| AppError::OperationFailed)?;
            messages.push(ChatMessage {
                id,
                role: ChatMessageRole::from_database_value(&role)?,
                body,
                created_at,
            });
        }

        messages.reverse();
        Ok(messages)
    }

    pub fn clear_chat_history(&self) -> Result<(), AppError> {
        let connection = self
            .connection
            .lock()
            .map_err(|_| AppError::OperationFailed)?;
        connection
            .execute("DELETE FROM chat_messages", [])
            .map_err(|_| AppError::OperationFailed)?;
        Ok(())
    }

    pub fn save_project_summary(&self, project: ProjectSummary) -> Result<(), AppError> {
        let connection = self
            .connection
            .lock()
            .map_err(|_| AppError::OperationFailed)?;
        connection
            .execute(
                "INSERT INTO projects (id, name, repo_path, worktree_path, branch, git_clean, changed_file_count, activity_state, activity_source, activity_observed_at) \
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10) \
                 ON CONFLICT(id) DO UPDATE SET name=excluded.name, repo_path=excluded.repo_path, worktree_path=excluded.worktree_path, branch=excluded.branch, git_clean=excluded.git_clean, changed_file_count=excluded.changed_file_count, activity_state=excluded.activity_state, activity_source=excluded.activity_source, activity_observed_at=excluded.activity_observed_at",
                params![
                    project.id,
                    project.name,
                    project.repo_path,
                    project.worktree_path,
                    project.branch,
                    if project.git_state.clean { 1_i64 } else { 0_i64 },
                    i64::from(project.git_state.changed_file_count),
                    project.activity.state.as_database_value(),
                    project.activity.source.as_database_value(),
                    project.activity.observed_at,
                ],
            )
            .map_err(|_| AppError::OperationFailed)?;
        Ok(())
    }

    pub fn add_project_root(&self, root: ProjectRoot) -> Result<ProjectRoot, AppError> {
        let connection = self
            .connection
            .lock()
            .map_err(|_| AppError::OperationFailed)?;
        let already_registered: bool = connection
            .query_row(
                "SELECT EXISTS(SELECT 1 FROM project_roots WHERE canonical_path = ?1)",
                [&root.path],
                |row| row.get(0),
            )
            .map_err(|_| AppError::OperationFailed)?;
        if already_registered {
            return Err(AppError::ProjectRootAlreadyRegistered);
        }

        let existing_project_id: Option<String> = connection
            .query_row(
                "SELECT id FROM projects WHERE repo_path = ?1 ORDER BY id LIMIT 1",
                [&root.path],
                |row| row.get(0),
            )
            .optional()
            .map_err(|_| AppError::OperationFailed)?;
        let project_id = if let Some(project_id) = existing_project_id {
            project_id
        } else {
            connection
                .execute(
                    "INSERT INTO projects (id, name, repo_path, worktree_path, branch, git_clean, changed_file_count, activity_state, activity_source, activity_observed_at) \
                     VALUES (?1, ?2, ?3, NULL, NULL, NULL, NULL, 'unknown', 'unknown', NULL)",
                    params![root.id, root.name, root.path],
                )
                .map_err(|_| AppError::OperationFailed)?;
            root.id.clone()
        };
        connection
            .execute(
                "INSERT INTO project_roots (project_id, canonical_path, added_at) VALUES (?1, ?2, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
                params![project_id, root.path],
            )
            .map_err(|_| AppError::OperationFailed)?;
        let mut root = root;
        root.id = project_id;
        Ok(root)
    }

    pub fn list_project_roots(&self) -> Result<Vec<ProjectRoot>, AppError> {
        let connection = self
            .connection
            .lock()
            .map_err(|_| AppError::OperationFailed)?;
        let mut statement = connection
            .prepare(
                "SELECT p.id, p.name, r.canonical_path \
                 FROM project_roots r JOIN projects p ON p.id = r.project_id \
                 ORDER BY p.name COLLATE NOCASE",
            )
            .map_err(|_| AppError::OperationFailed)?;
        let rows = statement
            .query_map([], |row| {
                Ok(ProjectRoot {
                    id: row.get(0)?,
                    name: row.get(1)?,
                    path: row.get(2)?,
                })
            })
            .map_err(|_| AppError::OperationFailed)?;
        rows.map(|row| row.map_err(|_| AppError::OperationFailed))
            .collect()
    }

    pub fn get_project_root(&self, project_id: String) -> Result<ProjectRoot, AppError> {
        let connection = self
            .connection
            .lock()
            .map_err(|_| AppError::OperationFailed)?;
        connection
            .query_row(
                "SELECT p.id, p.name, r.canonical_path \
                 FROM project_roots r JOIN projects p ON p.id = r.project_id \
                 WHERE p.id = ?1",
                [project_id],
                |row| {
                    Ok(ProjectRoot {
                        id: row.get(0)?,
                        name: row.get(1)?,
                        path: row.get(2)?,
                    })
                },
            )
            .optional()
            .map_err(|_| AppError::OperationFailed)?
            .ok_or(AppError::ProjectNotFound)
    }

    pub fn remove_project_root(&self, project_id: String) -> Result<(), AppError> {
        let connection = self
            .connection
            .lock()
            .map_err(|_| AppError::OperationFailed)?;
        let removed = connection
            .execute(
                "DELETE FROM project_roots WHERE project_id = ?1",
                [project_id],
            )
            .map_err(|_| AppError::OperationFailed)?;
        if removed == 0 {
            return Err(AppError::ProjectNotFound);
        }
        Ok(())
    }

    pub fn save_session_summary(&self, session: SessionSummary) -> Result<(), AppError> {
        let connection = self
            .connection
            .lock()
            .map_err(|_| AppError::OperationFailed)?;
        let project_exists: bool = connection
            .query_row(
                "SELECT EXISTS(SELECT 1 FROM projects WHERE id = ?1)",
                [&session.project_id],
                |row| row.get(0),
            )
            .map_err(|_| AppError::OperationFailed)?;
        if !project_exists {
            return Err(AppError::ProjectNotFound);
        }

        connection
            .execute(
                "INSERT INTO sessions (id, project_id, terminal_id, claude_session_id, agent, state, last_seen_at) \
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7) \
                 ON CONFLICT(id) DO UPDATE SET project_id=excluded.project_id, terminal_id=excluded.terminal_id, claude_session_id=excluded.claude_session_id, agent=excluded.agent, state=excluded.state, last_seen_at=excluded.last_seen_at",
                params![
                    session.id,
                    session.project_id,
                    session.terminal_id,
                    session.claude_session_id,
                    session.agent,
                    session.state.as_database_value(),
                    session.last_seen_at,
                ],
            )
            .map_err(|_| AppError::OperationFailed)?;
        Ok(())
    }

    pub fn set_preference(
        &self,
        key: String,
        value: String,
        updated_at: String,
    ) -> Result<(), AppError> {
        let connection = self
            .connection
            .lock()
            .map_err(|_| AppError::OperationFailed)?;
        connection
            .execute(
                "INSERT INTO preferences (key, value, updated_at) VALUES (?1, ?2, ?3) \
                 ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                params![key, value, updated_at],
            )
            .map_err(|_| AppError::OperationFailed)?;
        Ok(())
    }

    pub fn get_preference(&self, key: String) -> Result<Option<String>, AppError> {
        let connection = self
            .connection
            .lock()
            .map_err(|_| AppError::OperationFailed)?;
        connection
            .query_row(
                "SELECT value FROM preferences WHERE key = ?1",
                [key],
                |row| row.get(0),
            )
            .optional()
            .map_err(|_| AppError::OperationFailed)
    }
}
