use tauri::State;

use crate::domain::project::ProjectSummary;
use crate::domain::session::SessionSummary;
use crate::error::AppError;
use crate::store::Store;

#[tauri::command]
pub fn save_project_summary(
    store: State<'_, Store>,
    project: ProjectSummary,
) -> Result<(), AppError> {
    store.save_project_summary(project)
}

#[tauri::command]
pub fn save_session_summary(
    store: State<'_, Store>,
    session: SessionSummary,
) -> Result<(), AppError> {
    store.save_session_summary(session)
}
