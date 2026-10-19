use rusqlite::{Connection, Transaction};

use crate::error::AppError;

const CURRENT_SCHEMA_VERSION: i64 = 2;

const INITIAL_SCHEMA: &str = r#"
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    repo_path TEXT NOT NULL,
    worktree_path TEXT,
    branch TEXT,
    git_clean INTEGER,
    changed_file_count INTEGER,
    activity_state TEXT NOT NULL DEFAULT 'unknown',
    activity_source TEXT NOT NULL DEFAULT 'unknown',
    activity_observed_at TEXT
);

CREATE TABLE IF NOT EXISTS project_roots (
    project_id TEXT PRIMARY KEY NOT NULL,
    canonical_path TEXT NOT NULL UNIQUE,
    added_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY NOT NULL,
    project_id TEXT NOT NULL,
    terminal_id TEXT,
    claude_session_id TEXT,
    agent TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'unknown',
    last_seen_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS preferences (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    body TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at
    ON chat_messages(created_at DESC);

CREATE TABLE IF NOT EXISTS inbox_events (
    id TEXT PRIMARY KEY NOT NULL,
    session_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('output', 'approval', 'user_message', 'assistant_message', 'state_changed')),
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_inbox_events_created_at
    ON inbox_events(created_at DESC);
"#;

pub(super) fn migrate(connection: &mut Connection) -> Result<(), AppError> {
    let current_version: i64 = connection
        .pragma_query_value(None, "user_version", |row| row.get(0))
        .map_err(|_| AppError::OperationFailed)?;

    if current_version > CURRENT_SCHEMA_VERSION {
        return Err(AppError::OperationFailed);
    }

    if current_version == 0 {
        let transaction: Transaction<'_> = connection
            .transaction()
            .map_err(|_| AppError::OperationFailed)?;
        transaction
            .execute_batch(INITIAL_SCHEMA)
            .map_err(|_| AppError::OperationFailed)?;
        transaction
            .execute_batch("PRAGMA user_version = 2;")
            .map_err(|_| AppError::OperationFailed)?;
        transaction
            .commit()
            .map_err(|_| AppError::OperationFailed)?;
    }

    if current_version == 1 {
        let transaction: Transaction<'_> = connection
            .transaction()
            .map_err(|_| AppError::OperationFailed)?;
        transaction
            .execute_batch(
                "CREATE TABLE IF NOT EXISTS project_roots (\
                    project_id TEXT PRIMARY KEY NOT NULL,\
                    canonical_path TEXT NOT NULL UNIQUE,\
                    added_at TEXT NOT NULL,\
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE\
                );\
                PRAGMA user_version = 2;",
            )
            .map_err(|_| AppError::OperationFailed)?;
        transaction
            .commit()
            .map_err(|_| AppError::OperationFailed)?;
    }

    Ok(())
}
