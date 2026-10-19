use tauri::State;

use crate::domain::project::GitActivity;
use crate::error::AppError;
use crate::project_access::git;
use crate::store::Store;

#[tauri::command]
pub async fn get_git_activity(
    store: State<'_, Store>,
    project_id: String,
) -> Result<GitActivity, AppError> {
    let root = store.get_project_root(project_id)?;
    tauri::async_runtime::spawn_blocking(move || git::get_activity(root))
        .await
        .map_err(|_| AppError::OperationFailed)?
}
